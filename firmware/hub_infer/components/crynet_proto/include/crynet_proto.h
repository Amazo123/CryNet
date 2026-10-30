/*
 * CryNet — the node <-> hub wire protocol.
 *
 * This is the hub's copy of a contract that already exists in the node's
 * sketch (firmware/node/node_crynet/node_crynet.ino).  Both sides were
 * written from the same table, and this component exists so that the hub
 * has the layout in a place a compiler can check, rather than as prose in
 * a comment.
 *
 * Frame (node -> hub):
 *
 *     0  0xC3            magic
 *     1  0x7E            magic
 *     2  type            1 = telemetry, 2 = burst fragment
 *     3  node id
 *     4  u16 burst seq
 *     6  u16 frag index
 *     8  u16 frag count
 *    10  u16 payload len
 *    12  u16 payload CRC-16/CCITT-FALSE
 *    14  payload
 *    ..  u16 frame CRC-16/CCITT-FALSE over everything above
 *
 * A request (hub -> node) is twelve bytes.  It has no payload, so it
 * carries only the CRC of its first ten bytes:
 *
 *     0  0xC3  1 0x7E  2 type=3  3 node id
 *     4  u16 burst seq   6 u16 first fragment   8 u16 fragment count
 *    10  u16 CRC-16/CCITT-FALSE over the first ten bytes
 *
 * The telemetry payload is eight bytes: u32 rms x 1000, u16 window ms,
 * u8 flags, u8 reserved.
 */

#ifndef CRYNET_PROTO_H
#define CRYNET_PROTO_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define CRYNET_PROTO_MAGIC0        0xC3u
#define CRYNET_PROTO_MAGIC1        0x7Eu

#define CRYNET_PROTO_TYPE_TELEMETRY 1u
#define CRYNET_PROTO_TYPE_FRAGMENT  2u
#define CRYNET_PROTO_TYPE_REQUEST   3u
/* A heartbeat: the hub sends one every 100 ms so that its radio stays
 * awake.  A radio that is asleep between transmissions misses almost
 * everything the nodes send. */
#define CRYNET_PROTO_TYPE_HEARTBEAT 4u

#define CRYNET_PROTO_HEADER_BYTES  14u
#define CRYNET_PROTO_REQUEST_BYTES 12u

/* ESP-NOW carries at most 255 bytes in one frame. */
#define CRYNET_PROTO_MAX_FRAME     255u
#define CRYNET_PROTO_MAX_PAYLOAD   (CRYNET_PROTO_MAX_FRAME - CRYNET_PROTO_HEADER_BYTES - 2u)

/* The signal contract: 2 s of 16 kHz mono int16. */
#define CRYNET_PROTO_WINDOW_SAMPLES 32000u
#define CRYNET_PROTO_WINDOW_BYTES   (CRYNET_PROTO_WINDOW_SAMPLES * 2u)

/* A fragment carries this many payload bytes; the node's frame is
 * 14 + 224 + 2 = 240 bytes, comfortably inside the ESP-NOW limit. */
#define CRYNET_PROTO_FRAG_PAYLOAD   224u
#define CRYNET_PROTO_FRAG_COUNT     \
    ((CRYNET_PROTO_WINDOW_BYTES + CRYNET_PROTO_FRAG_PAYLOAD - 1u) / CRYNET_PROTO_FRAG_PAYLOAD)

/* The telemetry payload is 12 bytes. */
#define CRYNET_PROTO_TELEMETRY_BYTES 12u

/* Telemetry flags. */
#define CRYNET_PROTO_FLAG_BURST_READY   0x01u  /* the node has a frozen window  */
#define CRYNET_PROTO_FLAG_EVENT         0x02u  /* the node's event level is crossed */
#define CRYNET_PROTO_FLAG_WINDOW_FULL   0x04u  /* the live window holds 2 s     */

/* CRC-16/CCITT-FALSE: polynomial 0x1021, init 0xFFFF, no reflection. */
uint16_t crynet_proto_crc16(const uint8_t *data, size_t len);

/*
 * CRC-32, the IEEE 802.3 one: reflected, polynomial 0xEDB88320, init
 * 0xFFFFFFFF, final XOR 0xFFFFFFFF — the same function zlib's crc32()
 * computes.  The node puts this over its frozen window and advertises it
 * in the telemetry; the hub puts it over the window it reassembles from
 * the radio.  The two agreeing is the proof that the audio crossed the
 * link unchanged.
 */
uint32_t crynet_proto_crc32(const uint8_t *data, size_t len);

/*
 * Build a frame into `out`, which must have room for CRYNET_PROTO_MAX_FRAME
 * bytes.  Returns the total length including the trailing frame CRC, or 0
 * if the payload is too long.  A request frame (type 3) is built with the
 * twelve-byte layout; every other type uses the full header.
 */
size_t crynet_proto_build(uint8_t *out,
                           uint8_t type,
                           uint8_t node_id,
                           uint16_t seq,
                           uint16_t frag,
                           uint16_t frag_count,
                           const uint8_t *payload,
                           uint16_t payload_len);

/* Parse results. */
#define CRYNET_PROTO_BAD_FRAME    (-1)  /* malformed, or the frame CRC failed  */
#define CRYNET_PROTO_BAD_PAYLOAD  (-2)  /* the frame is sound, the payload is not */

/*
 * Parse a frame received from the radio.  On success the payload length is
 * returned (0 for a request) and the out parameters are filled in; for a
 * request, `payload` is set to NULL.  On failure one of the CRYNET_PROTO_BAD_*
 * codes is returned.
 */
int crynet_proto_parse(const uint8_t *data,
                        size_t len,
                        uint8_t *type,
                        uint8_t *node_id,
                        uint16_t *seq,
                        uint16_t *frag,
                        uint16_t *frag_count,
                        const uint8_t **payload);

/* Decode a telemetry payload. */
typedef struct {
    float    rms;        /* the node's 100 ms RMS, in full-scale units */
    uint16_t window_ms;  /* the length of the node's window           */
    uint8_t  flags;
    uint32_t frozen_crc; /* CRC-32 of the node's frozen window, 0 if none */
} crynet_proto_telemetry_t;

bool crynet_proto_decode_telemetry(const uint8_t *payload,
                                   size_t len,
                                   crynet_proto_telemetry_t *out);

#ifdef __cplusplus
}
#endif

#endif /* CRYNET_PROTO_H */
