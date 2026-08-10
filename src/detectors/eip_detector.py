from src.utils.aws_client import get_aws_client, get_target_regions
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Standard AWS idle Elastic IP price: $0.005/hour -> $3.60/month
EIP_MONTHLY_PRICE = 3.60

def detect_unused_eips() -> list:
    """
    Scans for Elastic IPs that are not associated with any resource.
    Excludes EIPs with opt-out tag: CostOptimizerOptOut=true.
    Supports multi-region scanning.
    """
    logger.info("Starting unused Elastic IP detection...")
    
    unused_eips = []
    target_regions = get_target_regions()
    
    for region in target_regions:
        logger.info(f"Scanning Elastic IPs in region: {region}")
        ec2_client = get_aws_client('ec2', region_name=region)
        
        try:
            # Note: describe_addresses doesn't support boto3 paginator
            response = ec2_client.describe_addresses()
            addresses = response.get('Addresses', [])
            
            for addr in addresses:
                # If AssociationId is missing, the Elastic IP is unassociated (unused)
                if 'AssociationId' not in addr:
                    public_ip = addr.get('PublicIp')
                    allocation_id = addr.get('AllocationId')
                    tags = addr.get('Tags', [])
                    
                    tag_dict = {tag['Key']: tag['Value'] for tag in tags}
                    
                    if tag_dict.get('CostOptimizerOptOut') == 'true':
                        logger.info(f"Elastic IP {public_ip} opted out of cleanup via tag.")
                        continue
                        
                    name = tag_dict.get('Name', 'Unnamed')
                    
                    logger.info(
                        f"[{region}] Detected Unused Elastic IP: IP={public_ip}, AllocationId={allocation_id}, "
                        f"Name={name}, Estimated Savings=${EIP_MONTHLY_PRICE}/mo"
                    )
                    
                    unused_eips.append({
                        'resource_id': allocation_id,  # use allocation_id for deletion/referencing
                        'resource_type': 'EIP',
                        'name': name,
                        'details': {
                            'region': region,
                            'public_ip': public_ip,
                            'domain': addr.get('Domain')
                        },
                        'estimated_monthly_savings': EIP_MONTHLY_PRICE,
                        'opt_out_tag': False
                    })
                    
        except ClientError as e:
            logger.error(f"Error describing Elastic IPs in region {region}: {e}")
            # Continue scanning other regions even if one fails
            continue
            
    logger.info(f"EIP scanning completed. Found {len(unused_eips)} unused Elastic IPs across all targeted regions.")
    return unused_eips

