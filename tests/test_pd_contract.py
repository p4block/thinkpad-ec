# SPDX-License-Identifier: WTFPL
"""Exercise actual PD decoder, fixed cache reads, errors, and stale-data gating."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]

class PDContract(unittest.TestCase):
    def test_contract_and_faults(self):
        code=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#include <errno.h>
typedef uint32_t u32;
typedef uint8_t u8;
#define module_param(...)
#define MODULE_PARM_DESC(...)
#define ACPI_FAILURE(x) (x)
#define EC_LOCK "test"
#define HZ 100
#define time_after_eq(a,b) ((long)((a)-(b))>=0)
static unsigned long jiffies;
static bool known_pd_layout;
static int cache_lock;
static void mutex_lock(int*p){assert(!*p);*p=1;}
static void mutex_unlock(int*p){assert(*p);*p=0;}
static int locks,reads,writes,busy,lock_error,fail_at,restore_error,denied,auths;
static u32 input[17];
static int acpi_acquire_mutex(void*p,char*s,int t){if(lock_error)return 1;locks++;return 0;}
static void acpi_release_mutex(void*p,char*s){assert(locks==1);locks--;}
static int ec_read(int a,u8*v){assert(locks==1);*v=a==0x90?busy:0x12;return 0;}
static int ec_write(int a,u8 v){assert(locks==1);writes++;return restore_error;}
static int read32(u32 a,u32*v){
 static const u32 off[]={0,0x14,0x1c,0x20};
 assert(locks==1&&reads<17);
 if(fail_at==reads)return -ETIMEDOUT;
 if(!reads&&denied){denied=0;*v=0;return 0;}
 if(!reads)assert(a==0x80368c);
 else {int n=reads-1;assert(a==0x80368c+(n/8)*0x90+off[n%4]);}
 *v=input[reads++];return 0;
}
static int unlock_debug(void){auths++;return 0;}
#include "t480-pd.h"
static void reset(void){
 memset(input,0,sizeof(input));
 input[0]=input[1]=input[5]=2; // disconnected PD0
 u32 port[]={2,0x78,0x45000000,0x641}; // PD1: 20V, 3.25A fixed PDO
 memcpy(input+9,port,sizeof(port));memcpy(input+13,port,sizeof(port));
 locks=reads=writes=busy=lock_error=restore_error=denied=auths=0;
 fail_at=-1;known_pd_layout=pd_contract=true;pd_attempted=false;jiffies=0;
 pd_mv[0]=pd_mv[1]=42;pd_errors[0]=pd_errors[1]=0;
}
static void set_pdo(u32 pdo){input[11]=input[15]=pdo<<24;input[12]=input[16]=pdo>>8;}
int main(void){
 long value=123;
 reset();assert(!read_pd(1,&value)&&value==20000&&reads==17&&writes==8&&!locks&&!cache_lock);
 assert(read_pd(0,&value)==-ENODATA&&value==20000&&reads==17);
 assert(!read_pd(1,&value)&&reads==17); // cached within one second
 // Disconnection must invalidate cached voltage, even if old PDO remains.
 input[10]=input[14]=0;jiffies=HZ;reads=writes=0;
 assert(read_pd(1,&value)==-ENODATA&&value==20000);
 reset();set_pdo((100u<<10)|300);assert(!read_pd(1,&value)&&value==5000);
 reset();set_pdo((180u<<10)|300);assert(!read_pd(1,&value)&&value==9000);
 reset();set_pdo((300u<<10)|300);assert(!read_pd(1,&value)&&value==15000);
 reset();set_pdo((401u<<10)|300);assert(read_pd(1,&value)==-ENODATA);
 reset();set_pdo(0xc0000000u|(100u<<10)|300);assert(read_pd(1,&value)==-ENODATA);
 reset();set_pdo(0x40000000u|(100u<<10)|300);assert(read_pd(1,&value)==-ENODATA);
 reset();set_pdo(400u<<10);assert(read_pd(1,&value)==-ENODATA);
 reset();input[10]=input[14]=0x58;assert(read_pd(1,&value)==-ENODATA); // source role
 reset();input[10]=input[14]=0x68;assert(read_pd(1,&value)==-ENODATA); // Type-C only
 reset();input[15]^=1;assert(read_pd(1,&value)==-EAGAIN&&pd_mv[1]==42);
 reset();denied=1;assert(!read_pd(1,&value)&&auths==1);
 reset();fail_at=3;assert(read_pd(1,&value)==-ETIMEDOUT&&!writes&&!locks);
 reset();restore_error=-EIO;assert(read_pd(1,&value)==-EIO&&writes==8&&pd_mv[1]==42);
 reset();busy=0x80;assert(read_pd(1,&value)==-EBUSY&&!writes&&!reads&&!locks);
 reset();lock_error=1;assert(read_pd(1,&value)==-EBUSY&&!writes&&!reads);
 reset();pd_contract=false;assert(read_pd(1,&value)==-ENODATA&&!reads);
 reset();known_pd_layout=false;assert(read_pd(1,&value)==-ENODATA&&!reads);
 reset();assert(read_pd(-1,&value)==-ENODATA&&read_pd(2,&value)==-ENODATA&&!reads);
 return 0;
}
'''
        with tempfile.TemporaryDirectory() as tmp:
            src,exe=Path(tmp)/'pd.c',Path(tmp)/'pd'
            src.write_text(code)
            subprocess.run(['cc','-std=c11','-fsanitize=undefined,bounds','-I',str(ROOT),str(src),'-o',str(exe)],check=True,capture_output=True)
            subprocess.run([str(exe)],check=True)
