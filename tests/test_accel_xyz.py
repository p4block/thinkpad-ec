# SPDX-License-Identifier: WTFPL
"""Exercise the driver's real frame decoder, including native signed axes."""
from pathlib import Path
import subprocess
import tempfile
import unittest


class Frames(unittest.TestCase):
    def test_decoding(self):
        source = (Path(__file__).parents[1] / "thinkpad_ec_accel.c").read_text()
        decoder = source[source.index("static int decode_frame("):source.index("static void poll_sensor(")]
        harness = r"""
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#include <errno.h>
typedef uint8_t u8;
typedef int16_t s16;
static unsigned get_unaligned_le16(const u8 *p) { return p[0] | (p[1] << 8); }
""" + decoder + r"""
static void put(u8 *p, int v) { p[0]=v; p[1]=(unsigned)v >> 8; }
static void record(u8 *p, int a, int b, int c) {
 put(p,a); put(p+2,b); put(p+4,c); p[6]=37;
}
int main(void) {
 u8 data[32]={0}; int axes[3]={99,98,97};
 assert(decode_frame(data,true,axes)==0 && axes[0]==99);
 data[0]=5; assert(decode_frame(data,true,axes)==-EPROTO);
 data[0]=6; assert(decode_frame(data,false,axes)==-EPROTO);
 data[0]=1; data[31]=1; assert(decode_frame(data,true,axes)==-EPROTO);
 data[31]=0;
 // Each input axis independently controls one output; include signed extremes.
 record(data+1,8000,-16000,24000);
 assert(decode_frame(data,true,axes)==1);
 assert(axes[0]==212 && axes[1]==412 && axes[2]==312);
 record(data+1,-32768,32767,-32768);
 assert(decode_frame(data,true,axes)==1);
 assert(axes[0]==921 && axes[1]==921 && axes[2]==921);
 // Truncate each native record before averaging, as the legacy formatter does.
 data[0]=4;
 record(data+1,-79,79,-79); record(data+8,-81,81,-81);
 record(data+15,-159,159,-159); record(data+22,-161,161,-161);
 assert(decode_frame(data,true,axes)==4);
 assert(axes[0]==513 && axes[1]==513 && axes[2]==513);
 // Four records end at byte 28; trailing metadata must not affect axes.
 data[29]=255; data[30]=255;
 assert(decode_frame(data,true,axes)==4 && axes[2]==513);
 // Existing X230 unsigned, five-record path is unchanged.
 memset(data,0,sizeof(data)); data[0]=5;
 for(int i=0;i<5;i++) { put(data+1+i*5,500+i); put(data+3+i*5,600+i); }
 assert(decode_frame(data,false,axes)==5);
 assert(axes[0]==502 && axes[1]==602);
 return 0;
}
"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "test.c").write_text(harness)
            subprocess.run(["cc", "-std=c11", "-O2", "-Wall", "-Werror",
                            "-fsanitize=undefined,bounds", str(root / "test.c"),
                            "-o", str(root / "test")], check=True, capture_output=True)
            subprocess.run([str(root / "test")], check=True)
