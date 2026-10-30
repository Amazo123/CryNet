idf_component_register(
    SRCS "node_link.c"
    INCLUDE_DIRS "include"
    COMPILE_DEFINITIONS "CRYNET_LINK_PROMISCUOUS=1"
    REQUIRES crynet_proto
    PRIV_REQUIRES esp_wifi esp_event esp_netif
)
