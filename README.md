# depenguin.me based order-and-provision script

We rely heavily on [depenguin.me](https://github.com/depenguin-me/depenguin-run) to make this happen. This script is basically just a little helper which executes some things neccessary to provision a server from a linux-Live-CD to persistent FreeBSD.

This script can also order servers from hetzner via the `-c` (regular servers) and `--market` (server market) flags.
We can provision servers (`-p` and `--no-hetzner`) from a regular linux-based Live-CD, too. This is tested and works with servers from leaseweb, OVH and hetzner so far.

## Usage
You can either rent the server through `provision.py` automatically (`-c` and `--market`), or provision an existing one which is bootet into a linux rescue (`-p`)

### Example for a generic server bootet into a linux rescue
```
$ ./provision.py --no-hetzner -p $your-IP --installerconfig myserver.txt
```

Where `myserver.txt` contains the installerconfig. See `installerconfig_hetzner.txt` for an example.

### Example with hetzner API
```
$ ./provision.py --api-password $my_pass -p $your-IP --installerconfig myserver.txt --hostname test.example.com
```

In this case we don't need any data in an installerconfig because we gather them directly from the hetzner API. You must provide `--api-user` and `--api-password` either via the commandline or set them in the config file `config.ini` (see `config.ini.example` for an example config file). Also you can set the name of the server directly on the commandline with `--hostname`.

### Example with automatically creating and provisioning a server
You can get the available servers and locations with `--list-types`:

```
$ provision.py --api-pw tops3cr3t --list-types
AX52 is available in HEL1: 68.187 (46.41 Setup)
AX52 is available in FSN1: 74.137 (46.41 Setup)
EX101 is available in HEL1: 97.937 (46.41 Setup)
EX101 is available in FSN1: 103.887 (46.41 Setup)
AX102 is available in HEL1: 121.737 (46.41 Setup)
AX102 is available in FSN1: 127.687 (46.41 Setup)
AX102 is available in NBG1: 127.687 (46.41 Setup)
EX44 is available in FSN1: 50.337 (46.41 Setup)
EX44 is available in HEL1: 44.387 (46.41 Setup)
EX130-R is available in FSN1: 163.387 (94.01 Setup)
EX130-R is available in HEL1: 157.437 (94.01 Setup)
EX130-S is available in FSN1: 163.387 (94.01 Setup)
EX130-S is available in HEL1: 157.437 (94.01 Setup)
AX162-S is available in FSN1: 246.687 (94.01 Setup)
AX162-S is available in HEL1: 234.787 (94.01 Setup)
AX162-R is available in FSN1: 246.687 (94.01 Setup)
AX162-R is available in HEL1: 234.787 (94.01 Setup)
GEX44 is available in FSN1: 216.937 (94.01 Setup)
AX42 is available in FSN1: 56.287 (46.41 Setup)
AX42 is available in HEL1: 52.717 (46.41 Setup)
SX65 is available in FSN1: 127.687 (46.41 Setup)
SX65 is available in HEL1: 121.737 (46.41 Setup)
SX135 is available in FSN1: 246.687 (94.01 Setup)
SX135 is available in HEL1: 240.737 (94.01 Setup)
SX295 is available in FSN1: 472.787 (94.01 Setup)
SX295 is available in HEL1: 454.937 (94.01 Setup)
```

You can now pass the desired server and the desired location (FSN1 by default) to `provision.py` to let it order and provision a server directly:

```
$ provision.py --api-pw t0ps3cr3t -c AX52 --location HEL1 --hostname test02.example.com
```

or, if you would like to rent one from the market, just note the ID and pass that to `-m`:

```
$ provision.py --api-pw t0ps3cr3t --market $id --hostname test03.example.com
2024-08-01 10:22:13,339 - INFO - Generated temporary password: KAVSKQCoLw3KfeI4jufNvT6kzcLE2WJcRbzP8Kmr_Vw
2024-08-01 10:22:13,986 - INFO - Transaction ID: random-id
2024-08-01 10:22:13,986 - INFO - Waiting for transaction to become ready...
2024-08-01 10:23:14,292 - INFO - Waiting for transaction to become ready...
2024-08-01 10:24:14,627 - INFO - Waiting for transaction to become ready...
2024-08-01 10:25:15,111 - INFO - Waiting for transaction to become ready...
2024-08-01 10:26:15,512 - INFO - Waiting for transaction to become ready...
2024-08-01 10:27:15,754 - INFO - Waiting for transaction to become ready...
2024-08-01 10:27:15,754 - INFO - Transaction ready.
2024-08-01 10:27:16,204 - INFO - Writing Hostname test03.example.con to API
2024-08-01 10:27:16,874 - INFO - Waiting for $ip4 to respond to SSH on Port 22...
2024-08-01 10:27:16,908 - INFO - Server became available
2024-08-01 10:27:16,908 - INFO - Starting Depenguin...
2024-08-01 10:27:59,772 - INFO - Waiting for $ip4 to respond to SSH on Port 1022...
2024-08-01 10:27:59,803 - INFO - Server became available
2024-08-01 10:27:59,803 - INFO - Depenguin is started
2024-08-01 10:28:00,313 - INFO - Destroying zpool: zroot
2024-08-01 10:28:04,081 - INFO - Wrote install_$ip4.txt as installerconfig
2024-08-01 10:28:04,082 - INFO - Uploading Installerconfig...
2024-08-01 10:28:04,422 - INFO - Running Installer
2024-08-01 10:28:57,167 - INFO - Waiting until install is finished and VM is shutdown...
2024-08-01 10:29:57,172 - INFO - Rebooting Host...
2024-08-01 10:30:07,247 - INFO - Waiting for $ip4 to respond to SSH on Port 22...
2024-08-01 10:32:10,835 - INFO - Server became available
2024-08-01 10:32:11,479 - INFO - Downloading post-provision script
2024-08-01 10:32:11,665 - INFO - Executing post-provision.sh
2024-08-01 10:32:23,048 - INFO - Connect to: admin@$ip4
2024-08-01 10:32:23,049 - INFO - IPv6 : admin@$ip6
```
