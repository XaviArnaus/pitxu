https://www.cyberciti.biz/faq/how-to-create-disk-image-on-mac-os-x-with-dd-command/

# Making disk image with dd using live CD/DVD or USB pen drive

You can boot from a live cd or USB pen drive. Once booted, make sure no partitions are mounted from the source hard drive disk. You can store disk image on an external USB disk. The syntax is as follows:

```
dd if=/dev/INPUT/DEVICE-NAME-HERE conv=sync,noerror bs=64K | gzip -c > /path/to/my-disk.image.gz
```

In this example, create disk image for `/dev/da0` i.e. cloning `/dev/da0` and save in the current directory:

```
dd if=/dev/da0 conv=sync,noerror bs=1024K | gzip -c > centos-core-7.gz
```

The above command just cloned the entire hard disk, including the MBR, bootloader, all partitions, UUIDs, and data.


# How to restore system (dd image)

The syntax is:

```
gunzip -c IMAGE.HERE-GZ | dd of=/dev/OUTPUT/DEVICE-HERE
```

For example:
```
gunzip -c centos-core-7.gz | dd of=/dev/da0
```
