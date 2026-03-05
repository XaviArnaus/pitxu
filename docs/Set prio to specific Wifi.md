# Set specific Wifi with higher prio

The goal is to connect preferently to a specific Wifi when available, over other Wifi connections configured in `nmtui`
https://www.baeldung.com/linux/wifi-connection-priority-order

## 1. Show available connections
```
nmcli con show
```

## 2. Show the metric that tells the prio of a specific Wifi connection

```
nmcli con show CATALUNYA_LLIURE | grep ipv4.route-metric
nmcli con show CATALUNYA_LLIURE | grep connection.autoconnect-priority
```

## 3. Set the metric to a highest number above the others
⚠️ The following didn't work.
```
sudo nmcli con modify CATALUNYA_LLIURE ipv4.route-metric 100
```

Trying now this:
```
sudo nmcli con modify CATALUNYA_LLIURE connection.autoconnect-priority 10
```

## 4. Start the connection
```
sudo nmcli connection up CATALUNYA_LLIURE
```

## 5. Restart the network manager service
```
sudo systemctl restart NetworkManager
```

# Notes

Take a look at this (both together):
https://askubuntu.com/questions/1348220/how-does-networkmanager-choose-which-wifi-network-to-connect-to-when-muliple-are?noredirect=1&lq=1
https://unix.stackexchange.com/questions/615085/automatically-reconnecting-to-wifi

*TL;DR:*
> `NetworkManager` does not choose which network to connect to at all; instead, `wpa_supplicant` does. `NetworkManager` simply tries to keep every active connection online, and then it delegates the work to other utilities based on the type of connection involved. For wireless and certain wired 802.1x connections, that's the job of `wpa_supplicant`