"""Test script: send random 32-bit values over UART via DIO1 (TX) and DIO0 (RX)

Usage: run from project root: python test_uart_dio1_dio0.py

This script:
- opens the first available WaveForms device
- configures UART on DIO1 (tx) and DIO0 (rx)
- sends N random 32-bit values as 4-byte little-endian sequences
- reads back any response and prints hex dumps
"""
import sys
import time
import random
import argparse
from WF_SDK import device
from WF_SDK.protocol import uart
from WF_SDK import scope

green_color = "\033[92m"
red_color = "\033[91m"
yellow_color = "\033[93m"
cyan_color = "\033[96m"
pink_color = "\033[38;5;218m"
reset_color = "\033[0m"


def to_bytes_le(value):
    """Convert a 32-bit integer to little-endian bytes."""
    return value.to_bytes(4, byteorder='little')


def read_response(dev, timeout=0.2, poll_interval=0.02):
    deadline = time.time() + timeout
    out = []
    while time.time() < deadline:
        try:
            rx = uart.read(dev)
        except Exception as e:
            print(f" read error: {e}")
            return out
        if rx:
            out.extend(rx)
        time.sleep(poll_interval)
    return out


def parse_response(rx_bytes):
    # rx_bytes is a list of ints
    b = bytes(rx_bytes)
    # look for compact binary ACK: 0xAA 0x55 + 4-byte value LE + 4-byte counter LE (10 bytes)
    # EXAMPLE: b'\xAA\x55\x34\x12\x00\x00\x01\x00\x00\x00' -> value=0x00001234, counter=1
    idx = b.find(b"\xAA\x55")
    if idx != -1 and len(b) >= idx + 10:
        off = idx
        val = int.from_bytes(b[off+2:off+6], 'little')
        counter = int.from_bytes(b[off+6:off+10], 'little')
        return { 'type': 'ack', 'value': val, 'counter': counter, 'raw': b }
    # header found but not enough bytes yet
    if idx != -1 and len(b) < idx + 10:
        return { 'type': 'incomplete', 'raw': b }
    # otherwise try to decode as UTF-8 text (replace errors)
    try:
        text = b.decode('utf-8', errors='replace')
        return { 'type': 'text', 'text': text, 'raw': b }
    except Exception:
        return { 'type': 'raw', 'raw': b }


def main(count=10, delay=0.1, baud=9600, rx_dio=0, tx_dio=1, timeout=0.2, seed=None, start=0, step=1):
    print("Opening device...")
    try:
        dev = device.open()
    except Exception as e:
        print(f"Failed to open device: {e}")
        return
    print(f"Opened device: {dev.name} (version {dev.version})")

    print(f"Configuring UART: RX=DIO{rx_dio}, TX=DIO{tx_dio}, baud={baud}")
    try:
        uart.open(dev, rx=rx_dio, tx=tx_dio, baud_rate=baud, parity=None, data_bits=8, stop_bits=1)
        # initialize scope with default settings (sampling frequency, buffer size)
        try:
            scope.open(dev, amplitude_range=7.5)
        except Exception:
            # non-fatal if scope open fails; measure() will still attempt a measurement
            pass
    except Exception as e:
        print(f"Failed to configure UART: {e}")
        device.close(dev)
        return

    try:
        recv_buffer = bytearray()
        total_sent = 0
        total_recv = 0
        t0 = time.perf_counter()
        for i in range(count):
            val = (start + (i * step)) & 0xFFFFFFFF # 32 bit mask and wrap-around
            payload = to_bytes_le(val)  # convert val to little-endian bytes
            print(f"[{i+1}/{count}] Sending 0x{val:08X} -> bytes: {payload}")
            try:
                uart.write(dev, payload)
                total_sent += len(payload)
            except Exception as e:
                print(f" write error: {e}")
                break
            rx = read_response(dev, timeout=timeout)
            if rx:
                total_recv += len(rx)
                # accumulate into recv_buffer and attempt to parse
                recv_buffer.extend(rx)
                parsed = parse_response(list(recv_buffer))
                if parsed['type'] == 'incomplete':
                    # give the device a short moment to finish sending the ACK
                    extra_deadline = time.time() + min(0.05, timeout)
                    while time.time() < extra_deadline:
                        extra = read_response(dev, timeout=0.01)
                        if extra:
                            recv_buffer.extend(extra)
                        time.sleep(0.005)
                    parsed = parse_response(list(recv_buffer))
                if parsed['type'] == 'ack':
                    # consume up to end of ACK (header + 10 bytes)
                    hdr_idx = recv_buffer.find(b"\xAA\x55")
                    if hdr_idx != -1:
                        del recv_buffer[:hdr_idx+10]
                else:
                    # if parse returned 'text', clear buffer after printing
                    recv_buffer.clear()
                if parsed['type'] == 'ack':
                    print(f" ACK: value={pink_color}0x{parsed['value']:08X}{reset_color} dec={parsed['value']} counter={parsed['counter']}")
                    # measure analog voltage on scope channel 1 (pins 1+ / 1-)
                    try:
                        voltage = scope.measure(dev, 1)
                        print(f" Scope CH1 voltage: {cyan_color}{voltage:.6f} V{reset_color}")
                    except Exception as e:
                        print(f" Scope measure error: {e}")
                elif parsed['type'] == 'text':
                    print(f" Text: {parsed['text']!r}")
                else:
                    print(f" Raw bytes: {parsed['raw']}")
            else:
                print(" No response")
            time.sleep(delay)

        print("Done sending. Cleaning up.")
        t1 = time.perf_counter()
        duration = t1 - t0
        print(f"Test duration: {duration:.3f} s")
        if count > 0:
            print(f"Average per-iteration: {duration/count*1000:.3f} ms")
        print(f"Total bytes sent: {total_sent}, total bytes received: {total_recv}")
    finally:
        try:
            uart.close(dev)
        except Exception:
            pass
        device.close(dev)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Send random 32-bit values over UART using DIO pins')
    parser.add_argument('-n', '--count', type=int, default=10, help='number of values to send')
    parser.add_argument('-b', '--baud', type=int, default=9600, help='baud rate')
    parser.add_argument('--delay', type=float, default=0.1, help='delay between sends (s)')
    parser.add_argument('--rx', type=int, default=0, help='DIO pin used for RX')
    parser.add_argument('--tx', type=int, default=1, help='DIO pin used for TX')
    parser.add_argument('--timeout', type=float, default=0.2, help='response timeout (s)')
    parser.add_argument('--seed', type=int, default=None, help='random seed')
    parser.add_argument('--start', type=int, default=0, help='start value for 32-bit counter')
    parser.add_argument('--step', type=int, default=7, help='step increment for counter')
    args = parser.parse_args()
    main(count=args.count, delay=args.delay, baud=args.baud, rx_dio=args.rx, tx_dio=args.tx, timeout=args.timeout, seed=args.seed, start=args.start, step=args.step)

"""Example: to send a full 32-bit wrap test starting near max"""
# python .\test_uart_dio1_dio0.py -n 4 --start 4294967294 --step 1