/* SPDX-License-Identifier: WTFPL */
/* N24HT37W cached TPS65988 active sink PDOs. No PD commands or policy writes. */
static bool pd_contract;
module_param(pd_contract, bool, 0400);
MODULE_PARM_DESC(pd_contract, "Enable firmware-checked T480 USB-C negotiated voltage reads");
static unsigned long pd_sampled;
static bool pd_attempted;
static int pd_errors[2];
static long pd_mv[2];

/* Two bracketing copies: flags, transformed Power Status, PDO low/high words. */
static int pd_decode(const u32 *words, long *value)
{
 u32 pdo, status = words[1];
 long mv;
 if (memcmp(words, words + 4, 4 * sizeof(u32))) return -EAGAIN;
 if (!(words[0] & 2) || (status & 0x60) != 0x60 ||
     ((status >> 3) & 3) != 3) return -ENODATA;
 /* PDO begins at unaligned record +0x1f. Fixed PDO voltage uses 50 mV. */
 pdo = (words[2] >> 24) | (words[3] << 8);
 if (pdo >> 30) return -ENODATA; /* Variable/battery/PPS needs other semantics. */
 mv = ((pdo >> 10) & 0x3ff) * 50;
 if (mv < 5000 || mv > 20000 || !(pdo & 0x3ff)) return -ENODATA;
 *value = mv;
 return 0;
}
static int pd_snapshot(void)
{
 static const u32 offsets[] = { 0, 0x14, 0x1c, 0x20 };
 u32 words[2][8];
 u8 saved[7], busy;
 int b, i, ret, restore;
 if (ACPI_FAILURE(acpi_acquire_mutex(NULL, EC_LOCK, 2000))) return -EBUSY;
 ret = ec_read(0x90, &busy);
 if (ret || (busy & 0x80)) { ret = ret ? ret : -EBUSY; goto unlock; }
 for (i = 0; i < 7; i++) { ret = ec_read(0x91 + i, &saved[i]); if (ret) goto unlock; }
 ret = read32(0x80368c, &words[0][0]);
 if (ret == -EACCES || (!ret && !words[0][0])) {
  ret = unlock_debug();
  if (!ret) ret = read32(0x80368c, &words[0][0]);
 }
 for (b = 0; !ret && b < 2; b++)
  for (i = 0; !ret && i < 8; i++)
   ret = read32(0x80368c + b * 0x90 + offsets[i % 4], &words[b][i]);
 if (ret != -ETIMEDOUT) {
  restore = ec_write(0x90, 0);
  for (i = 0; i < 7; i++) { int r = ec_write(0x91 + i, saved[i]); if (r) restore = r; }
  if (restore) ret = restore;
 }
 if (!ret)
  for (b = 0; b < 2; b++) pd_errors[b] = pd_decode(words[b], &pd_mv[b]);
unlock:
 acpi_release_mutex(NULL, EC_LOCK);
 return ret;
}
static int read_pd(int channel, long *value)
{
 int ret;
 if (channel < 0 || channel >= 2 || !pd_contract || !known_pd_layout) return -ENODATA;
 mutex_lock(&cache_lock);
 if (!pd_attempted || time_after_eq(jiffies, pd_sampled + HZ)) {
  ret = pd_snapshot();
  if (ret) pd_errors[0] = pd_errors[1] = ret;
  pd_sampled = jiffies;
  pd_attempted = true;
 }
 ret = pd_errors[channel];
 if (!ret) *value = pd_mv[channel];
 mutex_unlock(&cache_lock);
 return ret;
}
