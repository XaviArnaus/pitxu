# Improve the performance of the Raspberry Pi Zero 2W

Collecting some tricks to improve the performance of the small RPi Zero 2W.

## Parameters in the `config.txt`

Add / update / reduce to the following configurations in `/boot/firmware/config.txt`.
Be aware that it also depends on which components do we have connected to have Pitxu working (a `DSI` display does not need `i2c`, but a HAT soundcard most likely do). Be aware of your own configuration.

These configurations are intended to:
- limit whatever is loaded that may blow the memory or keep the system busy for no reason.
- Overclock a bit RAM & CPU frequency, and power voltage to 5V ≥ 2.4A

```
# Do not detect cameras
camera_auto_detect=0

# Do not detect DSI displays
display_auto_detect=0

# CPU overclock
force_turbo=0
over_voltage=6
arm_freq=1300
avoid_pwm_pll=1

# RAM overclock
sdram_freq=550
sdram_schmoo=0x02000020
over_voltage_sdram_p=6
over_voltage_sdram_i=4
over_voltage_sdram_c=4
over_voltage_sdram=2
temp_limit=80

# Keeping low power consumption disabling the following
hdmi_blanking=2
dtoverlay=disable-bt
```

## Disable Bluetooth services

We don't need them in Pitxu.
```
sudo systemctl disable hciuart.service
sudo systemctl disable bluealsa.service
sudo systemctl disable bluetooth.service
```

## Disable `hostapd`

We are not going to create a hotspot in the Raspberry Pi
```
sudo systemctl disable hostapd
```

## Swap file

It will fake more RAM using disk space.
Pros: Applications will not crash due to out of ram.
Cons: Uses disk, and most likely it's an SD card. This will destroy it in long term.

ToDo: Consider connecting a USB disk and place the swap file there.

### Setting up Swap with `rpi-swap`

From RPi OS Trixie on, the way is to use `rpi-swap`

1. Create the directory to override system defaults

    All files here are read by the system and rules here override system defaults.

    ```
    sudo mkdir /etc/rpi/swap.conf.d/
    ```

2. Create our swap config file.

    The file name is arbitrary.

    ```
    sudo nano /etc/rpi/swap.conf.d/fixedswapsize.conf
    ```

3. Add the configuration.

    Please note that this file has sections defined.
    Keep in mind

    ```
    [File]
    FixedSizeMiB=4096

    [Zram]
    #RamMultiplier=1
    FixedSizeMiB=4096
    ```

4. Reboot
5. Check that the file was created.

    ```
    ls -lh /var/swap

    -rw------- 1 root root 3.1G Jan  7 20:51 /var/swap
    ```


## Tools

### Get the memory and swap info

```
free -h
```

### How is swap set up in the system

It directly relates to the configuration in `/etc/rpi/swap.conf.d/fixedswapsize.conf` and `/etc/rpi/swap.conf`

```
sudo systemctl list-units --type swap
```

## Resources
https://discuss.moodlebox.net/d/391-raspberry-pi-zero-2-w-speed-up
https://pimylifeup.com/raspberry-pi-swap-file/


## Logs

### First run aftger setup:
1. Swap was only increased to ~400 MB
2. Pitxu OOM when leading the Vosk model.

```
cron invoked oom-killer: gfp_mask=0x140cca(GFP_HIGHUSER_MOVABLE|__GFP_COMP), order=0, oom_score_adj=0
CPU: 0 UID: 0 PID: 550 Comm: cron Tainted: G         C         6.12.62+rpt-rpi-v8 #1  Debian 1:6.12.62-1+rpt1
Tainted: [C]=CRAP
Hardware name: Raspberry Pi Zero 2 W Rev 1.0 (DT)
Call trace:
 dump_backtrace.part.0+0xe0/0x100
 show_stack+0x20/0x40
 dump_stack_lvl+0x60/0x80
 dump_stack+0x18/0x28
 dump_header+0x48/0x178
 oom_kill_process+0x29c/0x320
 out_of_memory+0xf4/0x5b0
 __alloc_pages_noprof+0xb0c/0xeb0
 alloc_pages_mpol_noprof+0x60/0x148
 vma_alloc_folio_noprof+0x88/0xe8
 do_swap_page+0x86c/0xd78
 __handle_mm_fault+0x1a0/0xc28
 handle_mm_fault+0xc4/0x2d8
 do_page_fault+0x13c/0x5a0
 do_translation_fault+0xb4/0xe0
 do_mem_abort+0x48/0xa0
 el0_da+0x2c/0xa0
 el0t_64_sync_handler+0xb4/0x130
 el0t_64_sync+0x190/0x198
Mem-Info:
active_anon:27124 inactive_anon:18649 isolated_anon:0
 active_file:176 inactive_file:40 isolated_file:0
 unevictable:0 dirty:3 writeback:0
 slab_reclaimable:4871 slab_unreclaimable:6491
 mapped:5 shmem:1 pagetables:1214
 sec_pagetables:0 bounce:0
 kernel_misc_reclaimable:0
 free:4345 free_pcp:142 free_cma:0
Node 0 active_anon:108496kB inactive_anon:74596kB active_file:780kB inactive_file:160kB unevictable:0kB isolated(anon):0kB isolated(file):0kB mapped:20kB dirty:12kB writeback:0kB shmem:4kB writeback_tmp:0kB kernel_stack:3024kB pagetables:4856kB sec_paget>
Node 0 DMA free:17380kB boost:0kB min:16384kB low:20480kB high:24576kB reserved_highatomic:0KB active_anon:46592kB inactive_anon:136500kB active_file:0kB inactive_file:1120kB unevictable:0kB writepending:12kB present:458752kB managed:426072kB mlocked:0kB>
lowmem_reserve[]: 0 0 0 0
Node 0 DMA: 45*4kB (U) 40*8kB (UE) 131*16kB (U) 123*32kB (UE) 45*64kB (UE) 21*128kB (UE) 9*256kB (UE) 6*512kB (U) 0*1024kB 0*2048kB 0*4096kB = 17476kB
572 total pagecache pages
292 pages in swap cache
Free swap  = 0kB
Total swap = 425980kB
114688 pages RAM
0 pages HighMem/MovableOnly
8170 pages reserved
65536 pages cma reserved
Tasks state (memory values in pages):
[  pid  ]   uid  tgid total_vm      rss rss_anon rss_file rss_shmem pgtables_bytes swapents oom_score_adj name
[    266]     0   266     7206       50       32       18         0    69632      256          -250 systemd-journal
[    316]   991   316    23057       59        0       59         0    77824      256             0 systemd-timesyn
[    324]     0   324     8788      126       32       94         0    73728      704         -1000 systemd-udevd
[    549]   101   549     1458      115       64       51         0    40960       32             0 avahi-daemon
[    550]     0   550     1745       92       32       60         0    49152        0             0 cron
[    551]   990   551     2103       92       64       28         0    49152      128          -900 dbus-daemon
[    553]   987   553    76918      106       64       42         0    81920      128             0 polkitd
[    558]     0   558     4713        0        0        0         0    65536      256             0 systemd-logind
[    564]   101   564     1414       96       37       59         0    36864        0             0 avahi-daemon
[    584]     0   584    85435      255      224       31         0   163840      608             0 NetworkManager
[    587]     0   587     4602       90       32       58         0    73728      416             0 wpa_supplicant
[    602]     0   602    81104       47        0       47         0   131072      416             0 ModemManager
[    880]     0   880     1926       80       32       48         0    45056        0             0 agetty
[    881]     0   881     1829       50        0       50         0    45056       32             0 agetty
[    885]     0   885     2863      114       64       50         0    49152      256         -1000 sshd
[    912]     0   912     5383       95       64       31         0    77824      416             0 sshd-session
[    917]  1000   917     5709       72        0       72         0    77824      544           100 systemd
[    919]  1000   919     5975       64        4       60         0    69632      384           100 (sd-pam)
[    937]  1000   937     1786      116       64       52         0    49152        0           200 mpris-proxy
[    942]  1000   942     1985       92       32       60         0    45056       32           200 dbus-daemon
[    944]  1000   944     5485      153       73       80         0    81920      512             0 sshd-session
[    945]  1000   945     2252      114       32       82         0    45056      576             0 bash
[    988]  1000   988     1422       62        0       62         0    36864       64             0 make
[    991]  1000   991      600       82        0       82         0    32768        0             0 sh
[    993]  1000   993     1421       95       32       63         0    40960       64             0 make
[    996]  1000   996   747929    30557    30557        0         0  1183744    31936             0 python
[   1018]  1000  1018     4950       79       32       47         0    61440     1408             0 python
[   1019]  1000  1019   210547      138      116       22         0   630784    32640             0 python
[   1024]  1000  1024     5391      215      128       87         0    69632     1472             0 python
[   1025]  1000  1025   212817    12717    12717        0         0   864256    39520             0 python
[   1030]  1000  1030   159057     2145     2106       39         0   454656    21824             0 python
oom-kill:constraint=CONSTRAINT_NONE,nodemask=(null),cpuset=/,mems_allowed=0,global_oom,task_memcg=/,task=python,pid=996,uid=1000
Out of memory: Killed process 996 (python) total-vm:2991716kB, anon-rss:122228kB, file-rss:0kB, shmem-rss:0kB, UID:1000 pgtables:1156kB oom_score_adj:0
```