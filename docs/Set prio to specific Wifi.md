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
```

## 3. Set the metric to a highest number above the others
```
sudo nmcli con modify CATALUNYA_LLIURE ipv4.route-metric 100
```

## 4. Start the connection
```
sudo nmcli connection up CATALUNYA_LLIURE
```

## 5. Restart the network manager service
```
sudo systemctl restart NetworkManager
```