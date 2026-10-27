# SPDX-License-Identifier: WTFPL
"""Compile actual cell decoder/transaction, including faults and cache commit."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

class T480Cells(unittest.TestCase):
    def test_decode_and_snapshot(self):
        code = r'''
#include <assert.h>
#include <stdint.h>
#include <string.h>
#include <stdlib.h>
#include <errno.h>
typedef uint32_t u32;
typedef uint8_t u8;
#define ARRAY_SIZE(a) (sizeof(a)/sizeof((a)[0]))
#define ACPI_FAILURE(x) (x)
#define EC_LOCK "test"
static long cells_mv[3];
static int lock_error,locks,busy,read_error,restore_error,timeout,unlocks;
static int reads,writes,denied,auth_error;
static u32 input[16];
static int acpi_acquire_mutex(void*p,const char*s,int t) {if(lock_error)return 1;locks++;return 0;}
static void acpi_release_mutex(void*p,const char*s) {assert(locks==1);locks--;}
static int ec_read(int a,u8*v) {assert(locks==1);*v=a==0x90?busy:0x12;return 0;}
static int ec_write(int a,u8 v) {assert(locks==1);writes++;return restore_error;}
static int read32(u32 a,u32*v) {
 assert(locks==1); if(timeout)return -ETIMEDOUT;if(read_error)return read_error;
 if(denied){denied=0;*v=0;return 0;}
 *v=input[reads++];return 0;
}
static int unlock_debug(void) {unlocks++;return auth_error;}
#include "t480-cells.h"
static void reset(void) {
 u32 valid[]={0x0a0018c4,0x0043474c,0x2d564e4c,0x56413130,0x00303234,
             12087,0x67016705,0x0fc10000,0x0fc00fc0,0x3008,
             0x67016705,0x0fc10000,0x0fc00fc0,0x3008,12087,0x0a0018c4};
 memcpy(input,valid,sizeof(input));
 lock_error=locks=busy=read_error=restore_error=timeout=unlocks=reads=writes=denied=auth_error=0;
 for(int i=0;i<3;i++)cells_mv[i]=42;
}
int main(void) {
 long values[3];
 reset();assert(!t480_cells_decode(input,values));
 assert(values[0]==4033&&values[1]==4032&&values[2]==4032);
 reset();assert(!t480_cells_snapshot()&&!locks&&writes==8);
 assert(cells_mv[0]==4033&&cells_mv[2]==4032);
 reset();denied=1;assert(!t480_cells_snapshot()&&unlocks==1&&cells_mv[0]==4033);
 reset();denied=1;auth_error=-EACCES;
 assert(t480_cells_snapshot()==-EACCES&&unlocks==1&&writes==8&&!locks&&cells_mv[0]==42);
 for(int index=0;index<16;index++) {
  reset();
  if(index==0||index==15)input[index]&=~4u;
  else input[index]^=0x8000;
  assert(t480_cells_snapshot()<0&&!locks&&cells_mv[0]==42);
 }
 reset();input[5]=input[14]=11000;assert(t480_cells_snapshot()==-EAGAIN);
 reset();input[7]=input[11]=0x00010000;assert(t480_cells_snapshot()==-ENODATA);
 reset();lock_error=1;assert(t480_cells_snapshot()==-EBUSY&&!writes&&!locks);
 reset();busy=0x80;assert(t480_cells_snapshot()==-EBUSY&&!writes&&!locks);
 reset();read_error=-EIO;assert(t480_cells_snapshot()==-EIO&&writes==8&&!locks&&cells_mv[0]==42);
 reset();restore_error=-EIO;assert(t480_cells_snapshot()==-EIO&&!locks&&cells_mv[0]==42);
 reset();timeout=1;assert(t480_cells_snapshot()==-ETIMEDOUT&&!writes&&!locks);
 return 0;
}
'''
        with tempfile.TemporaryDirectory() as tmp:
            src, exe = Path(tmp)/'cells.c', Path(tmp)/'cells'
            src.write_text(code)
            subprocess.run(['cc', '-std=c11', '-fsanitize=undefined,bounds', '-I', str(ROOT), str(src), '-o', str(exe)], check=True, capture_output=True)
            subprocess.run([str(exe)], check=True)
