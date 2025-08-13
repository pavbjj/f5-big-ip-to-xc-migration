import pandas as pd
import f5_bigip_config_module
import os.path

migration_sheet_path = './migration.xlsx'
bigip_config_path1 = './bigip.conf'
bigip_config_path2 = './profile_base.conf'

def automation_candidates():
    print("!!! Starting conversion of device: {}".format(migration_sheet_path))
    # Load the migration spreadsheet in a Pandas DataFrame
    migration_sheet_df = pd.read_excel(migration_sheet_path, sheet_name='Sheet1')

    # Filter all BIG-IP Virtual Servers which will be migrated using automation and save them in a new Pandas DataFrame
    migration_sheet_automation_df = migration_sheet_df.loc[
        (migration_sheet_df['XC compatible'] == "yes") & 
        (migration_sheet_df['Automation candidate'] == "yes") & 
        (migration_sheet_df['Load Balancer Type'] == "HTTP")
    ]

    # Generate a list with the name of all Virtual Servers which will be migrated
    vs_migrate_list = migration_sheet_automation_df['BIG-IP VS'].tolist()
    print("%s BIG-IP VSs will be migrated using automation." % len(vs_migrate_list))

    # Load the BIG-IP config (including the base/default profiles)
    bigip_config = f5_bigip_config_module.BigIPConfig(bigip_config_path1, bigip_config_path2)

    # Load the following BIG-IP TMOS objects: Virtual Servers, Pools & Profiles (HTTP, ClientSSL and ServerSSL)
    bigip_config_virtuals = bigip_config.list('ltm virtual')
    bigip_config_pools = bigip_config.list('ltm pool')
    bigip_config_profiles_http = bigip_config.list('ltm profile http')
    bigip_config_profiles_clientssl = bigip_config.list('ltm profile client-ssl')
    bigip_config_profiles_serverssl = bigip_config.list('ltm profile server-ssl')
    
    # Load the original spreadsheet to update it later
    df = pd.read_excel(migration_sheet_path)

    load_balancers = []
    for vs_migrate in vs_migrate_list:
        vs_migrate_basename = os.path.basename(vs_migrate)
        lb_fqdn = str(migration_sheet_automation_df.loc[migration_sheet_automation_df['BIG-IP VS'] == vs_migrate]['FQDN'].item())
        lb_namespace = str(migration_sheet_automation_df.loc[migration_sheet_automation_df['BIG-IP VS'] == vs_migrate]['XC Namespace'].item())
        lb_advertise_policy = str(migration_sheet_automation_df.loc[migration_sheet_automation_df['BIG-IP VS'] == vs_migrate]['Advertisment Policy (RE or CE)'].item())
        
        if lb_fqdn == "nan":
            lb_fqdn = ""
            print("Virtual Server FQDN is missing (%s)" % vs_migrate)
        
        found = 0
        # Look for the VS in the BIG-IP configuration
        for vs in bigip_config_virtuals:
            if vs.name == vs_migrate_basename:
                # VS was found in the BIG-IP configuration
                found = 1
                tls_termination = 0
                tls_reencryption = 0
                http_enabled = 0
                load_balancers_entry = {}
                lb_port = vs.properties['destination'].split(':')[1]
                for profile_name in vs.properties['profiles']:
                    profile_basename = os.path.basename(profile_name)
                    for profile in bigip_config_profiles_clientssl:
                        if profile_basename == profile.name:
                            tls_termination = 1
                            continue
                    for profile in bigip_config_profiles_serverssl:
                        if profile_basename == profile.name:
                            tls_reencryption = 1
                            continue
                    for profile in bigip_config_profiles_http:
                        if profile_basename == profile.name:
                            http_enabled = 1
                            continue
                
                if 'pool' not in vs.properties:
                    print("Virtual Server has no Default Pool (%s)" % vs_migrate)
                    df.loc[df['BIG-IP VS'] == vs.name, 'python_to_CSV'] = "Virtual Server has no Default Pool"
                    break
                
                pool_name = os.path.basename(vs.properties['pool'])
                for pool in bigip_config_pools:
                    if pool.name == pool_name:
                        members = []
                        monitors = []
                        for member in pool.properties['members']:
                            ip = os.path.basename(member).split(":")[0]
                            port = os.path.basename(member).split(":")[1]
                            members.append(ip)
                            hc = pool.properties.get('monitor')
                            monitors.append(hc)
                
                members_list = ';'.join(members)
                load_balancers_entry['ADO_ProjectName'] = ""
                load_balancers_entry['ADO_ReleasePipeline'] = ""
                load_balancers_entry['F5_Namespace'] = lb_namespace
                if lb_advertise_policy == "RE":
                    load_balancers_entry['PublishToInternet'] = "TRUE"
                elif lb_advertise_policy == "CE":
                    load_balancers_entry['PublishToInternet'] = ""
                else:
                    load_balancers_entry['PublishToInternet'] = "!No RE or CE!"
                load_balancers_entry['Frontend_FQDN'] = lb_fqdn
                load_balancers_entry['Backend_FQDN'] = ""
                load_balancers_entry['RootPath'] = ""
                load_balancers_entry['LoadBalancer_Description'] = "Automation Candidate"
                load_balancers_entry['F5_VirtualSite_Name'] = "ek--esxi--us-ga--dmz-prod"
                load_balancers_entry['F5_VirtualSite_Namespace'] = "shared"
                if lb_port == '80':
                    load_balancers_entry['LoadBalancer_Port'] = "80"
                    load_balancers_entry['LoadBalancer_DoNotRedirectHTTP'] = "TRUE/HTTP-only/TBC"
                else:
                    load_balancers_entry['LoadBalancer_Port'] = ""
                    load_balancers_entry['LoadBalancer_DoNotRedirectHTTP'] = ""
                load_balancers_entry['LoadBalancer_IdleTimeout'] = ""
                load_balancers_entry['LoadBalancer_ConnectionIdleTimeout'] = ""
                load_balancers_entry['OriginPool_IPAddresses'] = members_list
                load_balancers_entry['OriginPool_Port'] = port
                load_balancers_entry['OriginPool_SNIValue'] = ""
                load_balancers_entry['OriginPool_ConnectionTimeout'] = ""
                load_balancers_entry['OriginPool_HTTPIdleTimeout'] = ""
                if tls_reencryption == 0 and port not in ('443', '8443'):
                    load_balancers_entry['OriginPool_DisableTLS'] = "TRUE"
                else:
                    load_balancers_entry['OriginPool_DisableTLS'] = ""
                load_balancers_entry['Swagger_RelativePath'] = ""
                load_balancers_entry['HealthCheck_Namespace'] = lb_namespace
                load_balancers_entry['HealthCheck_Description'] = ""
                if hc is not None and ('icmp' not in hc and 'inband' not in hc):
                    load_balancers_entry['HealthCheck_TCP'] = ""
                else:
                    load_balancers_entry['HealthCheck_TCP'] = "TRUE"
                load_balancers_entry['HealthCheck_RelativePath'] = ""
                load_balancers_entry['HealthCheck_HealthyThreshold'] = ""
                load_balancers_entry['HealthCheck_Interval'] = ""
                load_balancers_entry['HealthCheck_Timeout'] = ""
                load_balancers_entry['HealthCheck_UnhealthyThreshold'] = ""
                load_balancers_entry['HealthCheck_ExpectedStatusCode'] = ""
                load_balancers_entry['HealthCheck_UseHTTP2'] = ""
                load_balancers_entry['F5_info_BIG_VS'] = vs.name
                load_balancers_entry['F5_info_tls_termination'] = tls_termination
                load_balancers_entry['F5_info_tls_reencryption'] = tls_reencryption
                load_balancers_entry['F5_info_health_check'] = hc
                load_balancers_entry['F5_info_http_enabled'] = http_enabled
                load_balancers.append(load_balancers_entry)

                # Enter information of automated VS back to original spreadsheet
                df.loc[df['BIG-IP VS'] == vs.name, 'python_to_CSV'] = "CSV generated"
                break

        if found == 0:
            print("Virtual Server (%s) not found." % vs_migrate)

    # Save the updates back to the spreadsheet
    df.to_excel(migration_sheet_path, index=False)

    load_balancers_df = pd.DataFrame(load_balancers)
    # print(load_balancers_df)
    load_balancers_df.to_csv('automation-candidates.csv', index=False)

if __name__ == '__main__':
    automation_candidates()
