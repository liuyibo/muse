# Muse

Muse is an intuitive framework designed to streamline the execution of commands on Android devices. By harnessing the capabilities of ADB (Android Debug Bridge), Muse offers a more efficient way to handle command execution, file management, and device interaction, making it an essential tool for developers and testers working with Android devices.

## 🚀 Key Features

- Simplified command execution on Android devices via ADB
- User-friendly job submission using straightforward commands
- Automated management of inputs/outputs, device states, and error handling
- Support for multi-user environments and device scheduling

## 🧩 Installation Guide

### On the Server

1. Install ADB:
   ```shell
   sudo apt-get update
   sudo apt-get install android-tools-adb
   ```
2. Follow the instructions to install MongoDB [here](https://www.mongodb.com/docs/manual/administration/install-on-linux/).
3. Use pip to install the Muse server package:
   ```shell
   pip3 install muse4ever[server]
   ```

### On the Client

1. Install the Muse client package with pip:
   ```shell
   pip3 install muse4ever
   ```
2. Configure the server address by setting the `MUSE_SERVER_ADDRESS` environment variable (default: `http://127.0.0.1:10813/`):
   ```shell
   export MUSE_SERVER_ADDRESS=<your_server_address>
   ```

## ⚙️ Configuring the Server

1. Start the MongoDB service:
   ```shell
   sudo systemctl start mongod
   ```
2. Initiate the Muse server (modify `MUSE_SERVER_HOST` and `MUSE_SERVER_PORT` as needed):
   ```shell
   export MUSE_SERVER_HOST=<host>
   export MUSE_SERVER_PORT=<port>
   muse-server
   ```
3. Start the Muse scheduler to manage job queues:
   ```shell
   muse-scheduler
   ```
4. Ensure that your Android devices are connected and recognized by ADB:
   ```shell
   adb devices
   ```

## 🧑‍💻 How to Use Muse

### Listing Connected Devices
```shell
muse devices
```

Sample output:

```
1 device(s) active
---------------------
10ADBG0DS2001R3
  Model: V2309A
  Battery Level: 100%
  Screen Status: off
```

### Executing Commands
```shell
muse run --dev <device_id> --cmd <command> [--in <input_files>] [--out <output_files>]
```

#### Example Usage 1
```shell
muse run --dev 10ADBG0DS2001R3 --cmd 'cat /proc/cpuinfo'
```
Output:
```
processor       : 0
BogoMIPS        : 26.00
Features        : fp asimd evtstrm aes pmull sha1 sha2 crc32 ...
CPU implementer : 0x41
CPU architecture: 8
...
```

#### Example Usage 2
```shell
echo "seq 1 10" > 1.txt
muse run --dev 10ADBG0DS2001R3 --cmd 'tac 1.txt > 2.txt' --in 1.txt --out 2.txt
cat 2.txt
```
Output:
```
10
9
8
7
6
5
4
3
2
1
```

## 📋 Notes
1. When specifying input and output files, use relative paths. For instance, if you run `muse run` with the input file `./123/456.txt`, it will be transferred to the device as `/data/local/tmp/muse/123/456.txt`.
2. Muse executes ADB commands under the hood; it doesn't provide environment isolation or resource constraints.
3. The Muse client communicates with the server using the HTTP protocol.
4. Developed by exzhawk, the name "muse4ever" is inspired by the "Love Live!" idol group μ's and was chosen as 'muse' was already taken in pypi 🎶🎶🎶


## Licensing
Muse is made available under the [MIT License](LICENSE).
