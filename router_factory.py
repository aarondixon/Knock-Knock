from routers.unifi import UnifiConfig, UnifiClient
import logging

logger = logging.getLogger(__name__)

def get_router(router_type):
    router_type = router_type.lower()
    if router_type == "unifi":
        config = UnifiConfig()
        config.validate()
        client = UnifiClient(config)
    else:
        raise ValueError(f"Unsupported router type: {router_type}")
    
    return client