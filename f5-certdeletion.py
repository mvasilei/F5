#! /usr/bin/env python
#This scripts deletes the unused certificates and keys from F5 LBs
#1. Checks the device is ACTIVE
#2. Checks the device is in sync
#3. compiles list of certs and keys to delete
#4. Deletes certs and key
#5. Performs config sync and saves config

import getpass, paramiko, time, signal, re, sys

def signal_handler(sig, frame):
    print('Exiting gracefully Ctrl-C detected...')
    sys.exit(0)

def connection_establishment(USER, PASS, host):
   try:
      client = paramiko.SSHClient()
      client.load_system_host_keys()
      client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
      client.connect(host, 22, username=USER, password=PASS)
      channel = client.invoke_shell()
      while not channel.recv_ready():
         time.sleep(1)

      channel.recv(65535)
   except paramiko.AuthenticationException as AuthError:
      print 'Authentication Error'
      sys.exit(0)
   except SSHException as sshException:
      print 'Unable to establish SSH connection' + sshException
      sys.exit(0)

   return (channel,client)

def connection_teardown(client):
   client.close()

def delete_certs_list(out, client):
   cert_list = []
   print 'Processing Certificate list...'
   for cert in out.splitlines():
      stdin, stdout, stderr = client.exec_command("grep " + cert + " /config/bigip.conf /config/partitions/*/bigip.conf|grep -v -e 'sys file ssl-cert' -e cache-path")
      usedCert = stdout.read()
      if usedCert == '':
         cert_list.append(cert)

   return (cert_list)

def delete_keys_list(cert_list, client):
   key_list = []
   print 'Processing Key list...'
   for cert in cert_list:
      stdin, stdout, stderr = client.exec_command("tmsh list sys crypto key " + cert.replace('.crt','') + ".key|grep crypto |awk '{print $4}'")
      usedKey = stdout.read().strip('\n')
      if usedKey != '':
         key_list.append(usedKey)

   return (key_list)

def delete_certs(cert_list, client):
   for cert in cert_list:
      stdin, stdout, stderr = client.exec_command("tmsh delete sys crypto cert " + cert)

def delete_keys(key_list, client):
   for key in key_list:
      stdin, stdout, stderr = client.exec_command("tmsh delete sys crypto key " + key)

def sync_save(client):
   stdin, stdout, stderr = client.exec_command("tmsh sho cm device-group|grep -iE -m 1 'failover|HA'|awk '{print $3}'")
   failover = stdout.read()
   if failover != '':
      client.exec_command("run cm config-sync to-group " + failover)

   client.exec_command("tmsh save sys config")

def is_active(client):
   stdin, stdout, stderr = client.exec_command("tmsh show cm failover-status")
   if 'ACTIVE' not in stdout.read():
      print 'Error: This device is Standby please execute the script on the Active device'
      connection_teardown(client)
      sys.exit(0)

def is_insync(client):
   stdin, stdout, stderr = client.exec_command("tmsh show cm sync-status")
   if 'green' not in stdout.read():
      print 'Error: This device is not in sync'
      connection_teardown(client)
      sys.exit(0)

def main(argv):
   if len(sys.argv) != 2:
     print 'Usage: ./f5-certdeletion.py <host_fqdn>'
     sys.exit(0)

   PASS = getpass.getpass(prompt='Enter ROOT password: ')
   channel,client = connection_establishment('root', PASS, argv[0])

   is_active(client)
   is_insync(client)

   stdin, stdout, stderr = client.exec_command("tmsh list sys crypto cert|awk '/crt/ {print $4}'|grep -Ev 'ca-bundle|default.crt|f5-irule.crt|intermediate'|sed '/^[[:space:]]*$/d'")
   out = stdout.read()

   cert_list = delete_certs_list(out, client)
   print 'List of certificates to be deleted...\n', cert_list
   key_list = delete_keys_list(cert_list, client)
   print 'List of keys to be deleted...\n', key_list

   delete_certs(cert_list,client)
   delete_keys(key_list,client)
   sync_save(client)



   connection_teardown(client)

if __name__ == '__main__':
   signal.signal(signal.SIGINT, signal_handler)  # catch ctrl-c and call handler to terminate the script
   main(sys.argv[1:])
