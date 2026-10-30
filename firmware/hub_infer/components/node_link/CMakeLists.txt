idf_component_register(
    SRCS "node_link.c"
    INCLUDE_DIRS "include"
    REQUIRES crynet_proto
    PRIV_REQUIRES esp_wifi esp_event esp_netif
)

# ESP-IDF 6 dropped the COMPILE_DEFINITIONS keyword from
# idf_component_register; an unknown keyword is silently swallowed as a
# value of the keyword before it, which made this component's include
# directory nonsense.  A target_compile_definitions call is the way now.
target_compile_definitions(${COMPONENT_LIB} PRIVATE "CRYNET_LINK_PROMISCUOUS=1")
