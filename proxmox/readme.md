# Prepare Ubuntu image
## disable cloud init
```
  sudo dpkg-reconfigure cloud-init
  sudo apt-get purge cloud-init
  sudo rm -rf /etc/cloud/ && sudo rm -rf /var/lib/cloud/
```

## remove snap
```
  sudo apt remove --autoremove snapd
  touch /etc/apt/preferences.d/nosnap.pref
    add ^
        Package: snapd
        Pin: release a=*
        Pin-Priority: -10
```

## install qemu agent
```
    apt update && apt -y install qemu-guest-agent
    systemctl enable qemu-guest-agent
```

# prox-manage.py script
```
  prox-manage.py --setup 2  # setup two new VMs
  prox-manage.py --teardown  # remove all agent instances (created by command above)
```