/* SPDX-License-Identifier: WTFPL */
/* N24HT37W BAT0 cache, LGC LNV-01AV420 only. Never infer vendor layouts. */
static int t480_cells_decode(const u32 *words, long *values)
{
 /* flags, maker, model[3], pack-before, vendor[4], vendor-repeat[4],
  * pack-after, flags-after. Words are native little-endian RAM values.
  */
 long sum = 0, pack_before = words[5] & 0xffff, pack_after = words[14] & 0xffff;
 int i;
 if (!(words[0] & 4) || !(words[15] & 4) ||
     words[1] != 0x0043474c || /* LGC\0 */
     words[2] != 0x2d564e4c || words[3] != 0x56413130 ||
     words[4] != 0x00303234) /* LNV-01AV420\0 */
  return -ENODATA;
 if (memcmp(words + 6, words + 10, 4 * sizeof(u32))) return -EAGAIN;
 /* Observed vendor format prefix; extra model/firmware gating is essential. */
 if (words[6] != 0x67016705 || (words[7] & 0xffff)) return -ENODATA;
 values[0] = words[7] >> 16;
 values[1] = words[8] & 0xffff;
 values[2] = words[8] >> 16;
 for (i = 0; i < 3; i++) {
  if (values[i] < 2000 || values[i] > 4500) return -ENODATA;
  sum += values[i];
 }
 /* Pack and vendor data are independently cached: reject load-step mismatch. */
 if (abs(sum - pack_before) > 100 || abs(sum - pack_after) > 100)
  return -EAGAIN;
 return 0;
}
static int t480_cells_snapshot(void)
{
 static const u32 addresses[] = {
  0x800fd4, 0x801028, 0x801038, 0x80103c, 0x801040, 0x801004,
  0x801058, 0x80105c, 0x801060, 0x801064,
  0x801058, 0x80105c, 0x801060, 0x801064, 0x801004, 0x800fd4
 };
 u32 words[ARRAY_SIZE(addresses)];
 u8 saved[7], busy;
 long values[3];
 int i, ret, restore;
 if (ACPI_FAILURE(acpi_acquire_mutex(NULL, EC_LOCK, 2000))) return -EBUSY;
 ret = ec_read(0x90, &busy);
 if (ret || (busy & 0x80)) { ret = ret ? ret : -EBUSY; goto unlock; }
 for (i = 0; i < 7; i++) { ret = ec_read(0x91 + i, &saved[i]); if (ret) goto unlock; }
 ret = read32(addresses[0], &words[0]);
 /* Unlike G2HT35WW, denied N24HT37W reads can return zero. */
 if (ret == -EACCES || (!ret && !words[0])) {
  ret = unlock_debug();
  if (!ret) ret = read32(addresses[0], &words[0]);
 }
 for (i = 1; !ret && i < ARRAY_SIZE(addresses); i++) ret = read32(addresses[i], &words[i]);
 if (ret != -ETIMEDOUT) {
  restore = ec_write(0x90, 0);
  for (i = 0; i < 7; i++) { int r = ec_write(0x91 + i, saved[i]); if (r) restore = r; }
  if (restore) ret = restore;
 }
 if (!ret) ret = t480_cells_decode(words, values);
 if (!ret) memcpy(cells_mv, values, sizeof(values));
unlock:
 acpi_release_mutex(NULL, EC_LOCK);
 return ret;
}
