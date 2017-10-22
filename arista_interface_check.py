#!/usr/local/bin/python3.5

import argparse
import re
import sys
import subprocess
import time

# Handling script parameters
parser = argparse.ArgumentParser()
parser.add_argument("dev_ip", help="Device IP address", type=str)
parser.add_argument("dev_comm", help="Device SNMP community string", type=str)
parser.add_argument("warning_level", help="Error pps count rising warning message", type=int)
parser.add_argument("critical_level", help="Error pps count rising critical message", type=int)
initial_args = parser.parse_args()

# Validating script parameters
if not (re.match("^([0-9]{1,3}\.){3}[0-9]{1,3}$", initial_args.dev_ip) and
        re.match("^[0-9a-zA-Z]+$", initial_args.dev_comm) and
        re.match("^[0-9]+$", str(initial_args.warning_level)) and
        re.match("^[0-9]+$", str(initial_args.critical_level)) and
        initial_args.warning_level < initial_args.critical_level):
    print("UNKNOWN - Wrong parameters")
    sys.exit(3)

'''
    Obtaining ethernet interfaces parameters:
    'snmpwalk' command with OID .1.3.6.1.2.1.2.2.1.2 displays names of all switch interfaces.
    'snmpwalk' command with OID .1.3.6.1.2.1.2.2.1.8 displays interfaces operating status.
    For IDs with 'Ethernet' in name and operating status 'up' script downloads in/out errors and discards.
    Counters are stored in dictionary {'interface name': {'id': , 'inDiscards': , 'inErrors': ,
                                                          'outDiscards': , 'outErrors': }}
'''
interfaces_data = {}
try:
    snmp_int_name = subprocess.check_output("snmpwalk -v 2c -On -c {0} {1} .1.3.6.1.2.1.2.2.1.2"
                                            .format(initial_args.dev_comm, initial_args.dev_ip), shell=True)
    snmp_int_status = subprocess.check_output("snmpwalk -v 2c -On -c {0} {1} .1.3.6.1.2.1.2.2.1.8"
                                              .format(initial_args.dev_comm, initial_args.dev_ip), shell=True)
    for id_line, status_line in zip(snmp_int_name.decode().splitlines(), snmp_int_status.decode().splitlines()):
        if re.search('Ethernet', id_line) and re.search('INTEGER: 1', status_line):
            interface_name = id_line.split()[-1]
            interface_id = id_line.split()[0].split('.')[-1]
            try:
                snmp_counters = subprocess.check_output("snmpget -v 2c -On -c {0} {1} .1.3.6.1.2.1.2.2.1.13.{2} "
                                                        ".1.3.6.1.2.1.2.2.1.14.{2} .1.3.6.1.2.1.2.2.1.19.{2} "
                                                        ".1.3.6.1.2.1.2.2.1.20.{2}"
                                                        .format(initial_args.dev_comm, initial_args.dev_ip,
                                                                interface_id), shell=True)
            except subprocess.CalledProcessError:
                print("UNKNOWN - SNMP error")
                sys.exit(3)

            counters_list = snmp_counters.decode().splitlines()
            interfaces_data[interface_name] = {'inDiscards': counters_list[0].split()[-1],
                                               'inErrors': counters_list[1].split()[-1],
                                               'outDiscards': counters_list[2].split()[-1],
                                               'outErrors': counters_list[3].split()[-1],
                                               'id': interface_id}

except subprocess.CalledProcessError:
    print("UNKNOWN - SNMP error")
    sys.exit(3)

'''
    After holding for 30 seconds updated counters are downloaded and subtracted from previous value.
    Next, clear interfaces and counters are removed from 'interfaces_data' dictionary.
'''
time.sleep(30)

for interface_name in interfaces_data:
    try:
        snmp_counters = subprocess.check_output("snmpget -v 2c -On -c {0} {1} .1.3.6.1.2.1.2.2.1.13.{2} "
                                                ".1.3.6.1.2.1.2.2.1.14.{2} .1.3.6.1.2.1.2.2.1.19.{2} "
                                                ".1.3.6.1.2.1.2.2.1.20.{2}"
                                                .format(initial_args.dev_comm, initial_args.dev_ip,
                                                        interfaces_data[interface_name]['id']), shell=True)
    except subprocess.CalledProcessError:
        print("UNKNOWN - SNMP error")
        sys.exit(3)

    counters_list = snmp_counters.decode().splitlines()
    interfaces_data[interface_name] = {'inDiscards': int(interfaces_data[interface_name]['inDiscards'])
                                       - int(counters_list[0].split()[-1]),
                                       'inErrors': int(interfaces_data[interface_name]['inErrors'])
                                       - int(counters_list[1].split()[-1]),
                                       'outDiscards': int(interfaces_data[interface_name]['outDiscards'])
                                       - int(counters_list[2].split()[-1]),
                                       'outErrors': int(interfaces_data[interface_name]['outErrors'])
                                       - int(counters_list[3].split()[-1])}

for interface_name in list(interfaces_data.keys()):
    if all(counter == 0 for counter in interfaces_data[interface_name].values()):
        interfaces_data.__delitem__(interface_name)
    else:
        for interface_key in list(interfaces_data[interface_name].keys()):
            if interfaces_data[interface_name][interface_key] == 0:
                interfaces_data[interface_name].__delitem__(interface_key)
            else:
                interfaces_data[interface_name][interface_key] /= -30

# Preparing results
warning_status = False
error_status = False
result = ''
for interface_name in list(interfaces_data.keys()):
    for interface_key in list(interfaces_data[interface_name].keys()):
        error_pps = interfaces_data[interface_name][interface_key]
        if error_pps > initial_args.critical_level:
            error_status = True
            result += "{0} {1}: {2}, ".format(interface_name, interface_key, error_pps)
        elif error_pps > initial_args.warning_level:
            warning_status = True
            result += "{0} {1}: {2}, ".format(interface_name, interface_key, error_pps)

# Returning status
if error_status:
    print("CRITICAL -", result[:-2])
    sys.exit(2)
elif warning_status:
    print("WARNING -", result[:-2])
    sys.exit(1)
else:
    print("OK", result)
    sys.exit(0)
