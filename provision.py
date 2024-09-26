#!/usr/bin/env python

import logging
import time
import requests
import simplejson as json
import configparser
from argparse import ArgumentParser
import logging
import secrets
from datetime import datetime
import socket
import paramiko
import sys
from jinja2 import Environment, FileSystemLoader

log = logging.getLogger(__name__)

ws_url = "https://robot-ws.your-server.de"
product_url = "/order/server/product"
create_product_url = "/order/server/transaction"
create_market_url = "/order/server_market/transaction"
get_server_url = "/server"
get_transaction_url = "/order/server/transaction"
get_market_url = "/order/server_market/transaction"
get_ip_url = "/ip"

default_dist = 'Rescue system'

config = configparser.ConfigParser()
config.read('config.ini')

parser = ArgumentParser()
parser.add_argument("-c", "--create", dest="create",
                    help="Create new Host (requires a type)")
parser.add_argument("--market", dest="market",
                    help="Buy Server ID from Marketplace")
parser.add_argument("--list-types", action="store_true")
parser.add_argument("--location", dest="location", default="FSN1",
                    help="Location for the new host (default: FSN1)")
parser.add_argument("-p" "--provision", dest="provision",
                    help="just provision a host. Needs IP and --sshpass to connect to")
parser.add_argument("--sshpass", dest="ssh_pass",
                    help="SSH Password to connect to rescue")
parser.add_argument("--no-ipv4", dest="ipv4",
                    default=True, action="store_false",
                    help="Don't Order IPv4 Addon")
parser.add_argument("--api-user", dest="api_user",
                    help="Robot Webservice User")
parser.add_argument("--api-pw", dest="api_password",
                    help="Robot Webservice Password")
parser.add_argument("-n", "--noop", dest="noop", default=False,
                    action='store_true', help="Noop, use for testing")
parser.add_argument("--no-hetzner", action="store_true", default=False,
                    dest="no_hetzner", help="Don't use hetzner API, just SSH to IP")
parser.add_argument("--installerconfig", dest="installerconfig",
                    help=".txt file to pass to depenguin. Only needed with --no-hetzner")
parser.add_argument("--log-level", default='info',
                    dest="log-level", help="Log Level")
parser.add_argument("--hostname", dest="hostname", default="hetzner",
                    help="Hostname to give to the host")
parser.add_argument("--post-provision",
                    help="URL to a script that gets downloaded and executed after the server is provisioned.")
parser.add_argument("--ssh-user", dest="ssh_user", help="User that gets added to the target system, required")

args = parser.parse_args()
a = vars(args)

logging.basicConfig(level=a['log-level'].upper(),
                    format='%(asctime)s - %(levelname)s - %(message)s')
logging.getLogger("paramiko").setLevel(logging.WARNING)
log.debug("Logging setup ready...")

def auth_get(url):
    if a['no_hetzner']:
        raise RuntimeError("Tried to call Hetzner API but --no-hetzner is given")
    log.debug("GET {}".format(url))
    r = requests.get(url, auth=(conf['api_user'], conf['api_password']))
    log.debug("Status Code: {}".format(r.status_code))
    log.debug("Response: {}".format(r.text))
    if r.status_code >= 200 and r.status_code < 300:
        return r.json()
    else:
        raise RuntimeError("API gave us an Error: {}".format(r.text))

def auth_post(url, data):
    if a['no_hetzner']:
        raise RuntimeError("Tried to call Hetzner API but --no-hetzner is given")
    log.debug("POST {} with {}".format(url, data))
    r = requests.post(url, data=data, auth=(conf['api_user'], conf['api_password']))
    log.debug("Status Code: {}".format(r.status_code))
    log.debug(r.text)
    if r.status_code >= 200 and r.status_code < 300:
        return r.json()
    else:
        raise RuntimeError("API gave us an Error: {}".format(r.text))

class Server(object):
    def __init__(self, result, ip=None):
        self.update_info(result)
        if ip is not None:
            self.ip = ip

    def get_ssh_connection(self, username='root', port=22):
        try:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            client.connect(self.ip, port=port,
                              username=username, look_for_keys=True)
        except Exception as e:
            log.error("Trouble connecting to SSH: {}".format(e))
            sys.exit(1)
        return client

    def update_info(self, result=None):
        if not no_hetzner:
            if result is None:
                result = auth_get(ws_url+get_server_url+'/{}'.format(self.number))
            data = result['server']
            self.number = data['server_number']
            self.ip = data['server_ip']
            self.status = data['status']
            self.dc = data['dc']
            self.ips = data['ip']
            self.ipv6_net = data['server_ipv6_net']
            self.name = data['server_name']

    def write_name(self, name):
        log.info("Writing Hostname {} to API".format(name))
        if no_hetzner:
            raise RuntimeError("Can not write the hostname on non-hetzner-Boxes")
        data = {
            'server_name': name
        }
        r = auth_post(ws_url+get_server_url+'/{}'.format(self.number), data)
        self.update_info()
        return r

    def check_ssh(self, port=22, timeout=5):
        success = True
        default_timeout = socket.getdefaulttimeout()
        socket.setdefaulttimeout(5)
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect((self.ip, port))
            s.close()
        except socket.error:
            success = False

        socket.setdefaulttimeout(default_timeout)
        return success

    def wait_for_ssh(self, port=22, patience=300):
        log.info("Waiting for {} to respond to SSH on Port {}..."
                 .format(self.ip, port))
        start_time = time.time()
        while True:
            current_time = time.time()
            if current_time > start_time + patience:
                log.info("Server {} did not come up after {} seconds."
                         .format(self.ip, patience))
                break
            is_up = self.check_ssh(port=port)
            if is_up:
                log.info("Server {} became available".format(self.ip))
                return
            time.sleep(5)

    def destroy_pool(self, pool="zroot"):
        disks = ['ada0', 'ada1']
        log.info("Destroying zpool: {}".format(pool))
        depenguin = self.get_ssh_connection(username='mfsbsd', port=1022)
        stdin, stdout, stderr = depenguin.exec_command(
            'sudo zpool export -f {}'.format(pool))
        log.debug("Export zpool: {}".format(stdout.read()))
        stdin, stdout, stderr = depenguin.exec_command(
            'sudo zpool destroy -f {}'.format(pool))
        log.debug("destroy zpool: {}".format(stdout.read()))
        for d in disks:
            for i in range(5):
                stdin, stdout, stderr = depenguin.exec_command(
                    'sudo zpool labelclear -f /dev/{}p{}'.format(d, i))
                log.debug("destroy zpool label: {}".format(stdout.read()))

            stdin, stdout, stderr = depenguin.exec_command(
                'sudo gpart destroy -F {}'.format(d))

    def create_installerconfig(self):
        env = Environment(loader=FileSystemLoader("{}".format(conf['installerconfig_path'])))
        tmpl = env.get_template("installertemplate_hetzner.txt")
        ip = auth_get(ws_url+get_ip_url+'/{}'.format(self.ip))
        data = {
            'ip': self.ip,
            'gateway': ip['ip']['gateway'],
            'ip6': self.ipv6_net+'2',
            'name': self.name,
            'user': conf['ssh_user']
        }
        filename = "{}/install_{}.txt".format(conf['installerconfig_path'], self.ip)
        content = tmpl.render(data)
        with open(filename, mode='w', encoding='utf-8') as f:
            f.write(content)
            log.info("Wrote {} as installerconfig".format(filename))
        return filename

    def run_bootstrap(self):
        ssh = self.get_ssh_connection(username=conf['ssh_user'])
        log.info("Downloading post-provision script")
        stdin, stdout, stderr = ssh.exec_command(
            'fetch -o post-provision.sh {}'.format(conf['post_provision']))
        log.debug("fetch output: {}".format(stdout.read()))

        log.info("Executing post-provision.sh")
        stdin, stdout, stderr = ssh.exec_command(
            'sudo sh post-provision.sh')
        log.debug("post-provision output: {}".format(stdout.read()))

    def auto_install(self):
        depenguin = self.get_ssh_connection(port=1022, username='mfsbsd')

        self.destroy_pool()

        if not no_hetzner:
            installerconfig = self.create_installerconfig()
        else:
            if a['installerconfig']:
                installerconfig = "{}/{}".format(conf['installerconfig_path'],
                                                 a['installerconfig'])
            else:
                raise ValueError("--no-hetzner requires --installerconfig")

        log.info("Uploading Installerconfig...")
        sftp = depenguin.open_sftp()
        sftp.put(installerconfig, 'depenguin_settings.sh')
        sftp.close()

        stdin, stdout, stderr = depenguin.exec_command(
            'sudo mv depenguin_settings.sh /root/ && sudo chmod +x /root/depenguin_settings.sh')
        log.debug("Chmod settings: {}".format(stdout.read()))

        log.info("Running Installer")
        stdin, stdout, stderr = depenguin.exec_command(
            'cd /root && sudo ./depenguin_bsdinstall.sh')
        log.debug("bsdinstall: {}".format(stdout.read()))

    def run_depenguin(self, ssh_pw=None):
        log.info("Starting Depenguin...")
        rescue = paramiko.SSHClient()
        rescue.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        if ssh_pw is not None:
            rescue.connect(self.ip, username="root", password=ssh_pw,
                           look_for_keys=False)
        else:
            rescue.connect(self.ip, username="root", look_for_keys=True)

        if 'image_url' in conf:
            stdin, stdout, stderr = rescue.exec_command(
                "wget -O run.sh {} && chmod +x run.sh && ./run.sh -m {} -d {}".format(
                    conf['run_url'], conf['image_url'], conf['authorized_keys']))
        else:
            stdin, stdout, stderr = rescue.exec_command(
                "wget -O run.sh {} && chmod +x run.sh && ./run.sh -d {}".format(
                    conf['run_url'], conf['authorized_keys']))

        log.debug(stdout.read())

        self.wait_for_ssh(port=1022)
        log.info("Depenguin is started")
        self.auto_install()
        log.info("Waiting until install is finished and VM is shutdown...")
        time.sleep(60)
        log.info("Rebooting Host...")
        stdin, stdout, stderr = rescue.exec_command("reboot")
        time.sleep(10)
        self.wait_for_ssh(port=22, patience=600)
        if self.check_ssh():
            if conf['post_provision']:
                self.run_bootstrap()
            log.info("Connect to: {}@{}".format(conf['ssh_user'], self.ip))
        if not no_hetzner:
            log.info("IPv6 : {}@{}2".format(conf['ssh_user'], self.ipv6_net))

    def _reboot(self):
        pass

class Transaction(object):
    def __init__(self, result, data, url=ws_url+get_transaction_url):
        self.update_info(result)
        self.url = url
        self.data = data

    def update_info(self, result=None):
        if result is None:
            result = auth_get(self.url+'/{}'.format(self.id))
        data = result['transaction']
        self.id = data['id']
        self.date = data['date']
        self.status = data['status']
        self.server_number = data['server_number']
        self.server_ip = data['server_ip']

    def wait_for_ready(self):
        while True:
            log.info("Waiting for transaction to become ready...")
            log.debug("current status: {}".format(self.status))
            if self.status == "ready":
                log.info("Transaction ready.")
                return
            if self.status == "cancelled":
                log.error("Transaction cancelled")
                return
            log.debug("waiting 1min...")
            time.sleep(60)
            self.update_info()

def get_server_by_number(number):
    try:
        result = auth_get(ws_url+get_server_url+'/{}'.format(number))
    except Exception as e:
        log.error("Could not find server: {}".format(e))
        sys.exit(1)
    return Server(result)

def get_server_by_ip(ip):
    if no_hetzner:
        return Server({}, ip=ip)

    try:
        result = auth_get(ws_url+get_ip_url+'/{}'.format(ip))
    except Exception as e:
        log.error("Could not find IP: {}".format(e))
        sys.exit(1)
    return get_server_by_number(result['ip']['server_number'])

def buy_product(product, url, data, ipv4=True, test=False):
    tmppw = password = secrets.token_urlsafe(32)
    log.info("Generated temporary password: {}".format(tmppw))
    data['password'] = tmppw
    if test:
        data['test'] = "true"
    if ipv4:
        data['addon[]'] = "primary_ipv4"

    try:
        r = auth_post(url, data)
    except Exception as e:
        log.error("Could not create Host: {}".format(e))
        sys.exit(1)

    log.info("Transaction ID: {}".format(r['transaction']['id']))
    log.debug("Transaction: {}".format(r['transaction']))
    return Transaction(r, data)

def create(product, location, ipv4=True, test=False):
    data = {
        'product_id': product,
        'location': location,
    }
    t = buy_product(product, ws_url+create_product_url, data, ipv4=ipv4, test=test)
    t.wait_for_ready()
    if t.status == "ready":
        server = get_server_by_number(t.server_number)
        server.write_name(a['hostname'])
        server.wait_for_ssh()
        server.run_depenguin(t.data['password'])
    else:
        log.error("Transaction did not finish! {}".format(t.status))

def buy_marketplace(product, ipv4=True, test=False):
    data = {
        'product_id': product,
    }
    t = buy_product(product, ws_url+create_market_url, data, ipv4=ipv4, test=test)
    t.url = ws_url+get_market_url
    t.wait_for_ready()
    if t.status == "ready":
        server = get_server_by_number(t.server_number)
        server.write_name(a['hostname'])
        server.wait_for_ssh()
        server.run_depenguin(t.data['password'])
    else:
        log.error("Transaction did not finish! {}".format(t.status))


def list_types():
    t = []
    r = auth_get(ws_url + product_url)
    for p in r:
        product = p['product']
        typ = {
            'id': product['id'],
            'location': product['location'],
            'prices': {}
        }
        for l in product['location']:
            for price in product['prices']:
                if price['location'] == l:
                    typ['prices'][l] = price
        t.append(typ)
    return t

log.debug("Invoked with: {}".format(a))
conf = dict(config['DEFAULT'])
no_hetzner = a['no_hetzner']

# merge config and arguments
if not no_hetzner:
    conf |= dict(config['hetzner'])

log.debug("Config: {}".format(conf))
merged = {
    k: (a.get(k) or conf.get(k))
    for k in set(a) | set(conf)
}
conf = merged
log.debug("Running with: {}".format(conf))

if not conf['ssh_user']:
    log.error("Can't work without a user. Please supply --user")
    sys.exit(1)

if not conf['authorized_keys']:
    log.error("Can't work without authorized_keys file. Please specify in config or argument.")
    sys.exit(1)

if conf['list_types']:
    t = list_types()
    for p in t:
        for l in p['location']:
            print("{} is available in {}: {} ({} Setup)".
                     format(p['id'],
                            l,
                            p['prices'][l]['price']['gross'],
                            p['prices'][l]['price_setup']['gross']))

if a['create']:
    if a['market']:
        log.error("Cant buy both, only -c or --market are possible")
        sys.exit(1)
    if no_hetzner:
        log.error("Can't create Servers outside of hetzner, but --no-hetzner is given")
        sys.exit(1)
    available_types = list_types()

    for available in available_types:
        if available['id'] == a['create']:
            if float(available['prices'][conf['location']]['price_setup']['gross']) > 0:
                log.warning("Setup Fees ahead!")
                log.warning("This Type has {} in Setup Fees in {}".
                            format(available['prices'][conf['location']]['price_setup']['gross'],
                                   conf['location']))
                log.warning("You can check with --list-types for any fees")
                log.warning("Kill this script now if you want to quit. Waiting 30s before continuing...")
                time.sleep(30)

    create(a['create'], conf['location'], ipv4=a['ipv4'], test=a['noop'])

if a['market']:
    if a['create']:
        log.error("Cant buy both, only -c or --market are possible")
        sys.exit(1)
    if no_hetzner:
        log.error("Can't create Servers outside of hetzner, but --no-hetzner is given")
        sys.exit(1)
    buy_marketplace(a['market'], test=a['noop'])

if a['provision']:
    log.info("Provisioning {}".format(a['provision']))
    if no_hetzner and not a['installerconfig']:
        log.error("--provision with --no-hetzner needs --installerconfig. Please create one first.")
        sys.exit(1)
    server = get_server_by_ip(a['provision'])
    server.wait_for_ssh()
    try:
        if a['ssh_pass']:
            server.run_depenguin(ssh_pw=a['ssh_pass'])
        else:
            server.run_depenguin()

    except Exception as e:
        log.error("Could not run depengiun: {}".format(e))
        sys.exit(1)
