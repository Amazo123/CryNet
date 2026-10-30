/*
 * CryNet — the node <-> hub wire protocol.  See crynet_proto.h.
 */

#include "crynet_proto.h"

#include <string.h>

uint16_t crynet_proto_crc16(const uint8_t *data, size_t len)
{
    uint16_t crc = 0xFFFFu;

    for (size_t i = 0; i < len; i++) {
        crc ^= (uint16_t)data[i] << 8;
        for (int bit = 0; bit < 8; bit++) {
            crc = (crc & 0x8000u) ? (uint16_t)((crc << 1) ^ 0x1021u)
                                  : (uint16_t)(crc << 1);
        }
    }
    return crc;
}

uint32_t crynet_proto_crc32(const uint8_t *data, size_t len)
{
    uint32_t crc = 0xFFFFFFFFu;

    for (size_t i = 0; i < len; i++) {
        crc ^= data[i];
        for (int bit = 0; bit < 8; bit++) {
            crc = (crc & 1u) ? ((crc >> 1) ^ 0xEDB88320u) : (crc >> 1);
        }
    }
    return crc ^ 0xFFFFFFFFu;
}

static void put_u16(uint8_t *p, uint16_t v)
{
    p[0] = (uint8_t)(v & 0xFFu);
    p[1] = (uint8_t)(v >> 8);
}

static uint16_t get_u16(const uint8_t *p)
{
    return (uint16_t)p[0] | ((uint16_t)p[1] << 8);
}

size_t crynet_proto_build(uint8_t *out,
                           uint8_t type,
                           uint8_t node_id,
                           uint16_t seq,
                           uint16_t frag,
                           uint16_t frag_count,
                           const uint8_t *payload,
                           uint16_t payload_len)
{
    if (type == CRYNET_PROTO_TYPE_REQUEST) {
        /* The twelve-byte request: no payload, no payload CRC. */
        out[0] = CRYNET_PROTO_MAGIC0;
        out[1] = CRYNET_PROTO_MAGIC1;
        out[2] = type;
        out[3] = node_id;
        put_u16(&out[4], seq);
        put_u16(&out[6], frag);
        put_u16(&out[8], frag_count);
        put_u16(&out[10], crynet_proto_crc16(out, 10));
        return CRYNET_PROTO_REQUEST_BYTES;
    }

    if (payload_len > CRYNET_PROTO_MAX_PAYLOAD) {
        return 0;
    }

    out[0] = CRYNET_PROTO_MAGIC0;
    out[1] = CRYNET_PROTO_MAGIC1;
    out[2] = type;
    out[3] = node_id;
    put_u16(&out[4], seq);
    put_u16(&out[6], frag);
    put_u16(&out[8], frag_count);
    put_u16(&out[10], payload_len);

    uint16_t pcrc = 0;
    if (payload_len > 0) {
        memcpy(&out[CRYNET_PROTO_HEADER_BYTES], payload, payload_len);
        pcrc = crynet_proto_crc16(payload, payload_len);
    }
    put_u16(&out[12], pcrc);

    const size_t total = CRYNET_PROTO_HEADER_BYTES + (size_t)payload_len;
    put_u16(&out[total], crynet_proto_crc16(out, total));
    return total + 2u;
}

int crynet_proto_parse(const uint8_t *data,
                        size_t len,
                        uint8_t *type,
                        uint8_t *node_id,
                        uint16_t *seq,
                        uint16_t *frag,
                        uint16_t *frag_count,
                        const uint8_t **payload)
{
    if (len < CRYNET_PROTO_REQUEST_BYTES) {
        return CRYNET_PROTO_BAD_FRAME;
    }
    if (data[0] != CRYNET_PROTO_MAGIC0 || data[1] != CRYNET_PROTO_MAGIC1) {
        return CRYNET_PROTO_BAD_FRAME;
    }

    const uint8_t t = data[2];
    if (t != CRYNET_PROTO_TYPE_TELEMETRY &&
        t != CRYNET_PROTO_TYPE_FRAGMENT &&
        t != CRYNET_PROTO_TYPE_REQUEST &&
        t != CRYNET_PROTO_TYPE_HEARTBEAT) {
        return CRYNET_PROTO_BAD_FRAME;
    }

    if (t == CRYNET_PROTO_TYPE_REQUEST || t == CRYNET_PROTO_TYPE_HEARTBEAT) {
        if (len != CRYNET_PROTO_REQUEST_BYTES) {
            return CRYNET_PROTO_BAD_FRAME;
        }
        if (crynet_proto_crc16(data, 10) != get_u16(&data[10])) {
            return CRYNET_PROTO_BAD_FRAME;
        }
        *type = t;
        *node_id = data[3];
        *seq = get_u16(&data[4]);
        *frag = get_u16(&data[6]);
        *frag_count = get_u16(&data[8]);
        *payload = NULL;
        return 0;
    }

    const uint16_t plen = get_u16(&data[10]);
    if (plen > CRYNET_PROTO_MAX_PAYLOAD) {
        return CRYNET_PROTO_BAD_FRAME;
    }
    const size_t total = CRYNET_PROTO_HEADER_BYTES + (size_t)plen;
    if (len != total + 2u) {
        return CRYNET_PROTO_BAD_FRAME;
    }
    if (crynet_proto_crc16(data, total) != get_u16(&data[total])) {
        return CRYNET_PROTO_BAD_FRAME;
    }

    *type = t;
    *node_id = data[3];
    *seq = get_u16(&data[4]);
    *frag = get_u16(&data[6]);
    *frag_count = get_u16(&data[8]);

    if (plen > 0) {
        if (crynet_proto_crc16(&data[CRYNET_PROTO_HEADER_BYTES], plen) != get_u16(&data[12])) {
            return CRYNET_PROTO_BAD_PAYLOAD;
        }
        *payload = &data[CRYNET_PROTO_HEADER_BYTES];
    } else {
        *payload = NULL;
    }
    return (int)plen;
}

bool crynet_proto_decode_telemetry(const uint8_t *payload,
                                   size_t len,
                                   crynet_proto_telemetry_t *out)
{
    if (payload == NULL || len < 12u) {
        return false;
    }

    const uint32_t rms_milli = (uint32_t)payload[0] |
                                ((uint32_t)payload[1] << 8) |
                                ((uint32_t)payload[2] << 16) |
                                ((uint32_t)payload[3] << 24);
    out->rms = (float)rms_milli / 1000.0f;
    out->window_ms = get_u16(&payload[4]);
    out->flags = payload[6];
    out->frozen_crc = (uint32_t)payload[8] |
                      ((uint32_t)payload[9] << 8) |
                      ((uint32_t)payload[10] << 16) |
                      ((uint32_t)payload[11] << 24);
    return true;
}
