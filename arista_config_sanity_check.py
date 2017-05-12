#!/usr/local/bin/python3.5

# Copyright (c) 2017, Atende Software
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

""" Arista config sanity checker.
    This script is searching for typos and misconfiguration by comparing created and assigned objects
    like ACLs, route-maps etc.
    Printed result is organised as in example below:

    Node: atds-test1
        Not assigned ACLs: test3, test4
        Not created ACLs: test2, test
        Not assigned as-path ACLs: ap-test
        Not created prefix-lists: longer_routes
        Not assigned route-maps: DCS_out, peer_in
        Not created route-maps: F1B_in

    Node: atds-test2
        Not assigned ACLs: operator_1
        ...

"""

# TODO handling eapi exceptions like inability to connect
# TODO temporary local copy of 'show run' instead of eapi request each time
# TODO VLANs

import pyeapi
import re
import smtplib


def gather_node_names(config='.eapi.conf'):
    """ Function for gathering node names for eAPI connections from given file or default .eapi.conf in local directory.
        Returns list of node names.
    """
    # Loading configuration file
    pyeapi.client.load_config(config)

    # Gathering node names
    nodes = []
    config_file = open(config)
    for line in config_file.readlines():
        if re.match('\[connection:', line):
            nodes.append(line.split(':')[1][:-2])
    return nodes


def send_email(message, recipient, config='.smtp.conf'):
    """ Function for sending message over SMTP server from configuration file containing three lines:
        login: user
        pass: password
        host: mail.example.com
    """
    smtp_data = {}
    smtp_config_file = open(config)
    for line in smtp_config_file.readlines():
        smtp_data[line.split(': ')[0]] = line.split(': ')[1].rstrip()

    smtp_connection = smtplib.SMTP(smtp_data['host'], 25)
    smtp_connection.starttls()
    smtp_connection.login(smtp_data['login'], smtp_data['pass'])
    email_header = 'To: ' + recipient + '\n' + 'From: ' + smtp_data['login'] + '\n' + 'Subject: Arista config check\n' \
                   + 'Content-Type: text/plain\n\n'
    email_message = email_header + message
    smtp_connection.sendmail(smtp_data['login'], recipient, email_message)
    smtp_connection.close()


#
def check_objects(check_type, return_message, eapi_connection, host_name):
    """ Function is gathering all created and assigned objects.
        Created objects are found by running proper 'show' command using eapi and parsing json response.
        Assigned objects comes from parsed 'show running configuration'.
        Returns dictionary with host_name as key containing list of alert messages.
    """
    created_objects = []
    default_objects = ''
    if check_type == 'acl':
        default_objects = ['.*bgp-ttlSec-ip-vrf-default.*', '^default-control-plane-acl$']
        created_command = 'show ip access-lists'
        result_key = 'aclList'
        assigned_command = '| include ip access-group'
        name_position = 2
    elif check_type == 'as-path':
        created_command = 'show ip as-path access-list'
        result_key = 'activeIpAsPathLists'
        assigned_command = '| include match as-path'
        name_position = 2
    elif check_type == 'prefix-list':
        created_command = 'show ip prefix-list'
        result_key = 'ipPrefixLists'
        assigned_command = '| include match ip address prefix-list'
        name_position = 4
    elif check_type == 'community-list':
        created_command = 'show ip community-list'
        result_key = 'ipCommunityLists'
        assigned_command = '| include match community'
        name_position = 2
    elif check_type == 'route-map':
        created_command = 'show route-map'
        result_key = 'routeMaps'
        assigned_command = '| grep \'neighbor .\+ route-map\|redistribute static route-map\|route install\''
        name_position = 3

    for created_object in eapi_connection.enable(created_command)[0]['result'][result_key]:
        if default_objects:
            if not re.match(default_objects[0], created_object['name']) and \
               not re.match(default_objects[1], created_object['name']):
                created_objects.append(created_object['name'])
        else:
            created_objects.append(created_object)
    assigned_objects = eapi_connection.get_config(params=assigned_command)[:-1]
    assigned_objects[:] = [element.lstrip().split()[name_position] for element in assigned_objects]

    # Removing duplicates
    assigned_objects = list(set(assigned_objects))

    # Preparing result dictionary with host_name's as keys
    if not len(created_objects) and not len(assigned_objects):
        return None
    else:
        not_assigned = [acl for acl in created_objects if acl not in assigned_objects]
        not_created = [acl for acl in assigned_objects if acl not in created_objects]
        result = {host_name: []}
        if not_assigned:
            result[host_name].append('Not assigned {0}: {1}'.format(return_message, ', '.join(not_assigned)))
        if not_created:
            result[host_name].append('Not created {0}: {1}'.format(return_message, ', '.join(not_created)))
        return result


# Proceeded if ran as a script
if __name__ == '__main__':
    """ For all nodes in eapi configuration file, check_objects is called for each check type.
        Results are added to final_result dictionary.
    """
    nodes_list = gather_node_names()
    # List of checks. Must match types in check_objects function.
    checked_parts = [['acl', 'ACLs'], ['as-path', 'as-path ACLs'], ['prefix-list', 'prefix-lists'],
                     ['community-list', 'community-lists'], ['route-map', 'route-maps']]
    final_result = {}
    for node in nodes_list:
        node_connection = pyeapi.connect_to(node)
        for check in checked_parts:
            returned_dictionary = check_objects(check[0], check[1], node_connection, node)
            if returned_dictionary:
                returned_key = list(returned_dictionary.keys())[0]
                if list(returned_dictionary.values())[0]:
                    if list(returned_dictionary.keys())[0] in final_result:
                        [final_result[returned_key].append(message) for message in returned_dictionary[returned_key]]
                    else:
                        final_result[returned_key] = returned_dictionary[returned_key]

    # Constructing readable output from final_result dictionary.
    alert_message = ''
    if final_result:
        for key in final_result:
            alert_message += "Node: {0}\n".format(key)
            for message in final_result[key]:
                alert_message += "\t{0}\n".format(message)
            alert_message += "\n"

    # Sending results over smtp
    if alert_message:
        send_email(alert_message, 'email@example.com')
