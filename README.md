* arista_interface_check

Python nagios script for monitoring errors and discards on Arista switch interfaces.  
Required parameters are:  
1) device IP address  
2) SNMP community string  
3) warning threshold (pps)  
4) error threshold (pps)  


* arista_config_sanity_check

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