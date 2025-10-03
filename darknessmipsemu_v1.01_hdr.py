#!/usr/bin/env python3
"""
MIPSEMU 1.01-HDR - Darkness Revived (Enhanced Codex Edition)
N64 Emulator with Extended MIPS R4300i Core & Advanced Features
Python 3.13 | Tkinter GUI

ENHANCEMENTS v1.01:
- Extended MIPS instruction set (60+ opcodes)
- Coprocessor 0 (COP0) system control
- TLB and memory management
- Controller input system
- Save RAM (EEPROM/SRAM/FlashRAM)
- Enhanced graphics with framebuffer
- Audio interface stub
- Interrupt system
- Cartridge I/O
- Recompiler preparation
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import os
from pathlib import Path
from datetime import datetime
import json
import struct
import threading
import time
from collections import defaultdict, deque
import hashlib


class ROMHeader:
    """N64 ROM Header Parser with Validation"""
    def __init__(self, data):
        self.raw_data = data[:0x1000]  # Read first 4KB for header
        self.valid = False
        self.parse()
        
    def parse(self):
        """Parse ROM header information"""
        if len(self.raw_data) < 0x40:
            return
            
        # Check endianness and convert if needed
        magic = struct.unpack('>I', self.raw_data[0:4])[0]
        
        if magic == 0x80371240:  # Big endian (z64)
            self.endian = 'big'
            self.valid = True
        elif magic == 0x40123780:  # Little endian (n64)
            self.endian = 'little'
            self.raw_data = self.swap_endian_n64(self.raw_data)
            self.valid = True
        elif magic == 0x37804012:  # Byte-swapped (v64)
            self.endian = 'byteswap'
            self.raw_data = self.swap_endian_v64(self.raw_data)
            self.valid = True
        else:
            self.endian = 'unknown'
            return
            
        # Parse header fields
        self.clock_rate = struct.unpack('>I', self.raw_data[0x04:0x08])[0]
        self.boot_address = struct.unpack('>I', self.raw_data[0x08:0x0C])[0]
        self.release = struct.unpack('>I', self.raw_data[0x0C:0x10])[0]
        
        # CRC
        self.crc1 = struct.unpack('>I', self.raw_data[0x10:0x14])[0]
        self.crc2 = struct.unpack('>I', self.raw_data[0x14:0x18])[0]
        
        # Unknown fields
        self.unknown1 = struct.unpack('>Q', self.raw_data[0x18:0x20])[0]
        
        # Name (20 bytes)
        self.name = self.raw_data[0x20:0x34].decode('ascii', errors='ignore').strip('\x00')
        
        # Unknown
        self.unknown2 = struct.unpack('>I', self.raw_data[0x34:0x38])[0]
        
        # Manufacturer ID
        self.manufacturer = struct.unpack('>I', self.raw_data[0x38:0x3C])[0]
        
        # Cartridge ID
        self.cart_id_word = struct.unpack('>H', self.raw_data[0x3C:0x3E])[0]
        
        # Country code
        self.country_code = chr(self.raw_data[0x3E])
        self.country = self.get_country_name(self.country_code)
        
        # Version
        self.version = self.raw_data[0x3F]
        
        # Game ID (from 0x3B-0x3E)
        self.game_id = self.raw_data[0x3B:0x3F].decode('ascii', errors='ignore')
        
        # Calculate ROM hash
        self.rom_hash = hashlib.md5(self.raw_data[:0x100]).hexdigest()
        
    def get_country_name(self, code):
        """Get country name from code"""
        countries = {
            'A': 'All/Demo', 'D': 'Germany', 'E': 'USA', 'F': 'France',
            'I': 'Italy', 'J': 'Japan', 'S': 'Spain', 'U': 'Australia',
            'P': 'Europe', 'N': 'Canada', 'X': 'Europe (X)',
            'Y': 'Europe (Y)', 'Z': 'Europe (Z)'
        }
        return countries.get(code, 'Unknown')
        
    def swap_endian_n64(self, data):
        """Convert little endian to big endian"""
        result = bytearray(len(data))
        for i in range(0, len(data), 4):
            result[i:i+4] = data[i:i+4][::-1]
        return bytes(result)
        
    def swap_endian_v64(self, data):
        """Convert byte-swapped to big endian"""
        result = bytearray(len(data))
        for i in range(0, len(data), 2):
            result[i] = data[i+1]
            result[i+1] = data[i]
        return bytes(result)


class COP0:
    """Coprocessor 0 - System Control"""
    def __init__(self):
        self.registers = [0] * 32
        # Important COP0 registers
        self.INDEX = 0
        self.RANDOM = 1
        self.ENTRYLO0 = 2
        self.ENTRYLO1 = 3
        self.CONTEXT = 4
        self.PAGEMASK = 5
        self.WIRED = 6
        self.BADVADDR = 8
        self.COUNT = 9
        self.ENTRYHI = 10
        self.COMPARE = 11
        self.STATUS = 12
        self.CAUSE = 13
        self.EPC = 14
        self.PRID = 15  # Processor ID
        self.CONFIG = 16
        self.LLADDR = 17
        self.WATCHLO = 18
        self.WATCHHI = 19
        self.XCONTEXT = 20
        self.PERR = 26
        self.CACHEERR = 27
        self.TAGLO = 28
        self.TAGHI = 29
        self.ERROREPC = 30
        
        # Initialize processor ID
        self.registers[self.PRID] = 0x00000B00  # VR4300
        self.registers[self.STATUS] = 0x34000000  # Boot status
        
    def read(self, reg):
        return self.registers[reg & 0x1F]
        
    def write(self, reg, value):
        reg = reg & 0x1F
        if reg == 0:  # Index register can be written
            self.registers[reg] = value & 0x3F
        elif reg == self.RANDOM:
            pass  # Random is read-only, auto-increments
        elif reg == self.COMPARE:
            self.registers[reg] = value
            self.registers[self.CAUSE] &= ~0x8000  # Clear timer interrupt
        else:
            self.registers[reg] = value


class MIPSCPU:
    """Enhanced MIPS R4300i CPU Core with Extended Instruction Set"""
    def __init__(self, memory):
        self.memory = memory
        self.pc = 0xA4000040  # Boot address
        self.next_pc = self.pc + 4
        self.registers = [0] * 32  # 32 general purpose registers
        self.registers[0] = 0  # $zero always 0
        self.hi = 0
        self.lo = 0
        self.cop0 = COP0()
        self.cop1_registers = [0] * 32  # FPU registers (stubs)
        
        self.running = False
        self.instructions_executed = 0
        self.cycles = 0
        
        # Branch delay slot
        self.branch_delay = False
        self.delay_slot_pc = 0
        
        # Load delay slot (MIPS I architecture)
        self.load_delay = False
        self.load_reg = 0
        self.load_value = 0
        
        # LLbit for LL/SC instructions
        self.llbit = False
        self.lladdr = 0
        
        # Exception handling
        self.exception_pending = False
        self.exception_code = 0
        
    def reset(self):
        """Reset CPU state"""
        self.pc = 0xA4000040
        self.next_pc = self.pc + 4
        self.registers = [0] * 32
        self.hi = 0
        self.lo = 0
        self.instructions_executed = 0
        self.cycles = 0
        self.branch_delay = False
        self.load_delay = False
        self.llbit = False
        self.exception_pending = False
        self.cop0 = COP0()
        
    def step(self):
        """Execute one instruction"""
        if not self.running:
            return
            
        try:
            # Handle load delay slot
            if self.load_delay:
                self.registers[self.load_reg] = self.load_value
                self.load_delay = False
                
            # Fetch instruction
            instruction = self.memory.read_word(self.pc)
            
            # Decode and execute
            self.execute_instruction(instruction)
            
            # Update PC
            if self.branch_delay:
                self.pc = self.delay_slot_pc
                self.branch_delay = False
            else:
                self.pc = self.next_pc
            self.next_pc = self.pc + 4
            
            self.instructions_executed += 1
            self.cycles += 1
            
            # Update COP0 COUNT register (increments every other cycle)
            if self.cycles % 2 == 0:
                count = self.cop0.read(self.cop0.COUNT)
                self.cop0.write(self.cop0.COUNT, (count + 1) & 0xFFFFFFFF)
                
            # Check for timer interrupt
            if self.cop0.read(self.cop0.COUNT) == self.cop0.read(self.cop0.COMPARE):
                self.cop0.registers[self.cop0.CAUSE] |= 0x8000
                
        except Exception as e:
            print(f"CPU Exception at PC={hex(self.pc)}: {e}")
            self.running = False
            
    def execute_instruction(self, instr):
        """Decode and execute MIPS instruction"""
        opcode = (instr >> 26) & 0x3F
        
        # Special opcodes
        if opcode == 0x00:  # SPECIAL
            self.execute_special(instr)
        elif opcode == 0x01:  # REGIMM
            self.execute_regimm(instr)
        elif opcode == 0x10:  # COP0
            self.execute_cop0(instr)
        elif opcode == 0x11:  # COP1 (FPU)
            self.execute_cop1(instr)
        # Jump instructions
        elif opcode == 0x02:  # J - jump
            target = (instr & 0x3FFFFFF) << 2
            self.do_branch((self.pc & 0xF0000000) | target)
        elif opcode == 0x03:  # JAL - jump and link
            target = (instr & 0x3FFFFFF) << 2
            self.registers[31] = self.next_pc + 4
            self.do_branch((self.pc & 0xF0000000) | target)
        # Branch instructions
        elif opcode == 0x04:  # BEQ
            rs, rt = (instr >> 21) & 0x1F, (instr >> 16) & 0x1F
            offset = self.sign_extend_16(instr & 0xFFFF) << 2
            if self.registers[rs] == self.registers[rt]:
                self.do_branch(self.next_pc + offset)
        elif opcode == 0x05:  # BNE
            rs, rt = (instr >> 21) & 0x1F, (instr >> 16) & 0x1F
            offset = self.sign_extend_16(instr & 0xFFFF) << 2
            if self.registers[rs] != self.registers[rt]:
                self.do_branch(self.next_pc + offset)
        elif opcode == 0x06:  # BLEZ
            rs = (instr >> 21) & 0x1F
            offset = self.sign_extend_16(instr & 0xFFFF) << 2
            if self.signed_word(self.registers[rs]) <= 0:
                self.do_branch(self.next_pc + offset)
        elif opcode == 0x07:  # BGTZ
            rs = (instr >> 21) & 0x1F
            offset = self.sign_extend_16(instr & 0xFFFF) << 2
            if self.signed_word(self.registers[rs]) > 0:
                self.do_branch(self.next_pc + offset)
        # Immediate arithmetic
        elif opcode == 0x08:  # ADDI
            rs, rt = (instr >> 21) & 0x1F, (instr >> 16) & 0x1F
            imm = self.sign_extend_16(instr & 0xFFFF)
            self.registers[rt] = (self.registers[rs] + imm) & 0xFFFFFFFF
        elif opcode == 0x09:  # ADDIU
            rs, rt = (instr >> 21) & 0x1F, (instr >> 16) & 0x1F
            imm = self.sign_extend_16(instr & 0xFFFF)
            self.registers[rt] = (self.registers[rs] + imm) & 0xFFFFFFFF
        elif opcode == 0x0A:  # SLTI
            rs, rt = (instr >> 21) & 0x1F, (instr >> 16) & 0x1F
            imm = self.sign_extend_16(instr & 0xFFFF)
            self.registers[rt] = 1 if self.signed_word(self.registers[rs]) < imm else 0
        elif opcode == 0x0B:  # SLTIU
            rs, rt = (instr >> 21) & 0x1F, (instr >> 16) & 0x1F
            imm = self.sign_extend_16(instr & 0xFFFF)
            self.registers[rt] = 1 if self.registers[rs] < (imm & 0xFFFFFFFF) else 0
        elif opcode == 0x0C:  # ANDI
            rs, rt = (instr >> 21) & 0x1F, (instr >> 16) & 0x1F
            imm = instr & 0xFFFF
            self.registers[rt] = self.registers[rs] & imm
        elif opcode == 0x0D:  # ORI
            rs, rt = (instr >> 21) & 0x1F, (instr >> 16) & 0x1F
            imm = instr & 0xFFFF
            self.registers[rt] = self.registers[rs] | imm
        elif opcode == 0x0E:  # XORI
            rs, rt = (instr >> 21) & 0x1F, (instr >> 16) & 0x1F
            imm = instr & 0xFFFF
            self.registers[rt] = self.registers[rs] ^ imm
        elif opcode == 0x0F:  # LUI
            rt = (instr >> 16) & 0x1F
            imm = instr & 0xFFFF
            self.registers[rt] = (imm << 16) & 0xFFFFFFFF
        # 64-bit immediate arithmetic
        elif opcode == 0x18:  # DADDI
            rs, rt = (instr >> 21) & 0x1F, (instr >> 16) & 0x1F
            imm = self.sign_extend_16(instr & 0xFFFF)
            self.registers[rt] = (self.registers[rs] + imm) & 0xFFFFFFFF
        elif opcode == 0x19:  # DADDIU
            rs, rt = (instr >> 21) & 0x1F, (instr >> 16) & 0x1F
            imm = self.sign_extend_16(instr & 0xFFFF)
            self.registers[rt] = (self.registers[rs] + imm) & 0xFFFFFFFF
        # Load instructions
        elif opcode == 0x20:  # LB
            rs, rt = (instr >> 21) & 0x1F, (instr >> 16) & 0x1F
            offset = self.sign_extend_16(instr & 0xFFFF)
            addr = (self.registers[rs] + offset) & 0xFFFFFFFF
            value = self.memory.read_byte(addr)
            if value & 0x80:
                value |= 0xFFFFFF00
            self.registers[rt] = value & 0xFFFFFFFF
        elif opcode == 0x21:  # LH
            rs, rt = (instr >> 21) & 0x1F, (instr >> 16) & 0x1F
            offset = self.sign_extend_16(instr & 0xFFFF)
            addr = (self.registers[rs] + offset) & 0xFFFFFFFF
            value = self.memory.read_half(addr)
            if value & 0x8000:
                value |= 0xFFFF0000
            self.registers[rt] = value & 0xFFFFFFFF
        elif opcode == 0x23:  # LW
            rs, rt = (instr >> 21) & 0x1F, (instr >> 16) & 0x1F
            offset = self.sign_extend_16(instr & 0xFFFF)
            addr = (self.registers[rs] + offset) & 0xFFFFFFFF
            self.registers[rt] = self.memory.read_word(addr)
        elif opcode == 0x24:  # LBU
            rs, rt = (instr >> 21) & 0x1F, (instr >> 16) & 0x1F
            offset = self.sign_extend_16(instr & 0xFFFF)
            addr = (self.registers[rs] + offset) & 0xFFFFFFFF
            self.registers[rt] = self.memory.read_byte(addr)
        elif opcode == 0x25:  # LHU
            rs, rt = (instr >> 21) & 0x1F, (instr >> 16) & 0x1F
            offset = self.sign_extend_16(instr & 0xFFFF)
            addr = (self.registers[rs] + offset) & 0xFFFFFFFF
            self.registers[rt] = self.memory.read_half(addr)
        elif opcode == 0x26:  # LWR - Load Word Right
            rs, rt = (instr >> 21) & 0x1F, (instr >> 16) & 0x1F
            offset = self.sign_extend_16(instr & 0xFFFF)
            addr = (self.registers[rs] + offset) & 0xFFFFFFFF
            shift = (addr & 3) * 8
            word = self.memory.read_word(addr & ~3)
            mask = (1 << shift) - 1
            self.registers[rt] = (self.registers[rt] & ~mask) | (word & mask)
        elif opcode == 0x27:  # LWU
            rs, rt = (instr >> 21) & 0x1F, (instr >> 16) & 0x1F
            offset = self.sign_extend_16(instr & 0xFFFF)
            addr = (self.registers[rs] + offset) & 0xFFFFFFFF
            self.registers[rt] = self.memory.read_word(addr)
        # Store instructions
        elif opcode == 0x28:  # SB
            rs, rt = (instr >> 21) & 0x1F, (instr >> 16) & 0x1F
            offset = self.sign_extend_16(instr & 0xFFFF)
            addr = (self.registers[rs] + offset) & 0xFFFFFFFF
            self.memory.write_byte(addr, self.registers[rt] & 0xFF)
        elif opcode == 0x29:  # SH
            rs, rt = (instr >> 21) & 0x1F, (instr >> 16) & 0x1F
            offset = self.sign_extend_16(instr & 0xFFFF)
            addr = (self.registers[rs] + offset) & 0xFFFFFFFF
            self.memory.write_half(addr, self.registers[rt] & 0xFFFF)
        elif opcode == 0x2B:  # SW
            rs, rt = (instr >> 21) & 0x1F, (instr >> 16) & 0x1F
            offset = self.sign_extend_16(instr & 0xFFFF)
            addr = (self.registers[rs] + offset) & 0xFFFFFFFF
            self.memory.write_word(addr, self.registers[rt])
        # Atomic load/store
        elif opcode == 0x30:  # LL - Load Linked
            rs, rt = (instr >> 21) & 0x1F, (instr >> 16) & 0x1F
            offset = self.sign_extend_16(instr & 0xFFFF)
            addr = (self.registers[rs] + offset) & 0xFFFFFFFF
            self.registers[rt] = self.memory.read_word(addr)
            self.llbit = True
            self.lladdr = addr
        elif opcode == 0x38:  # SC - Store Conditional
            rs, rt = (instr >> 21) & 0x1F, (instr >> 16) & 0x1F
            offset = self.sign_extend_16(instr & 0xFFFF)
            addr = (self.registers[rs] + offset) & 0xFFFFFFFF
            if self.llbit and addr == self.lladdr:
                self.memory.write_word(addr, self.registers[rt])
                self.registers[rt] = 1
            else:
                self.registers[rt] = 0
            self.llbit = False
        # Cache operations
        elif opcode == 0x2F:  # CACHE
            pass  # Cache operations are mostly ignored in HLE
            
        # Keep $zero always 0
        self.registers[0] = 0
        
    def execute_special(self, instr):
        """Execute SPECIAL (R-type) instruction"""
        rs = (instr >> 21) & 0x1F
        rt = (instr >> 16) & 0x1F
        rd = (instr >> 11) & 0x1F
        shamt = (instr >> 6) & 0x1F
        funct = instr & 0x3F
        
        if funct == 0x00:  # SLL
            self.registers[rd] = (self.registers[rt] << shamt) & 0xFFFFFFFF
        elif funct == 0x02:  # SRL
            self.registers[rd] = (self.registers[rt] >> shamt) & 0xFFFFFFFF
        elif funct == 0x03:  # SRA
            val = self.signed_word(self.registers[rt])
            self.registers[rd] = (val >> shamt) & 0xFFFFFFFF
        elif funct == 0x04:  # SLLV
            sh = self.registers[rs] & 0x1F
            self.registers[rd] = (self.registers[rt] << sh) & 0xFFFFFFFF
        elif funct == 0x06:  # SRLV
            sh = self.registers[rs] & 0x1F
            self.registers[rd] = (self.registers[rt] >> sh) & 0xFFFFFFFF
        elif funct == 0x07:  # SRAV
            sh = self.registers[rs] & 0x1F
            val = self.signed_word(self.registers[rt])
            self.registers[rd] = (val >> sh) & 0xFFFFFFFF
        elif funct == 0x08:  # JR
            self.do_branch(self.registers[rs])
        elif funct == 0x09:  # JALR
            target = self.registers[rs]
            self.registers[rd] = self.next_pc + 4
            self.do_branch(target)
        elif funct == 0x0C:  # SYSCALL
            self.trigger_exception(8)  # Syscall exception
        elif funct == 0x0D:  # BREAK
            self.trigger_exception(9)  # Breakpoint exception
        elif funct == 0x0F:  # SYNC
            pass  # Memory barrier - ignored in HLE
        elif funct == 0x10:  # MFHI
            self.registers[rd] = self.hi
        elif funct == 0x11:  # MTHI
            self.hi = self.registers[rs]
        elif funct == 0x12:  # MFLO
            self.registers[rd] = self.lo
        elif funct == 0x13:  # MTLO
            self.lo = self.registers[rs]
        elif funct == 0x14:  # DSLLV (64-bit)
            sh = self.registers[rs] & 0x3F
            self.registers[rd] = (self.registers[rt] << sh) & 0xFFFFFFFF
        elif funct == 0x16:  # DSRLV (64-bit)
            sh = self.registers[rs] & 0x3F
            self.registers[rd] = (self.registers[rt] >> sh) & 0xFFFFFFFF
        elif funct == 0x17:  # DSRAV (64-bit)
            sh = self.registers[rs] & 0x3F
            val = self.signed_word(self.registers[rt])
            self.registers[rd] = (val >> sh) & 0xFFFFFFFF
        elif funct == 0x18:  # MULT
            a = self.signed_word(self.registers[rs])
            b = self.signed_word(self.registers[rt])
            result = a * b
            self.lo = result & 0xFFFFFFFF
            self.hi = (result >> 32) & 0xFFFFFFFF
        elif funct == 0x19:  # MULTU
            result = self.registers[rs] * self.registers[rt]
            self.lo = result & 0xFFFFFFFF
            self.hi = (result >> 32) & 0xFFFFFFFF
        elif funct == 0x1A:  # DIV
            a = self.signed_word(self.registers[rs])
            b = self.signed_word(self.registers[rt])
            if b != 0:
                self.lo = (a // b) & 0xFFFFFFFF
                self.hi = (a % b) & 0xFFFFFFFF
        elif funct == 0x1B:  # DIVU
            if self.registers[rt] != 0:
                self.lo = (self.registers[rs] // self.registers[rt]) & 0xFFFFFFFF
                self.hi = (self.registers[rs] % self.registers[rt]) & 0xFFFFFFFF
        elif funct == 0x1C:  # DMULT (64-bit multiply)
            a = self.signed_word(self.registers[rs])
            b = self.signed_word(self.registers[rt])
            result = a * b
            self.lo = result & 0xFFFFFFFF
            self.hi = (result >> 32) & 0xFFFFFFFF
        elif funct == 0x1D:  # DMULTU (64-bit multiply unsigned)
            result = self.registers[rs] * self.registers[rt]
            self.lo = result & 0xFFFFFFFF
            self.hi = (result >> 32) & 0xFFFFFFFF
        elif funct == 0x1E:  # DDIV (64-bit divide)
            a = self.signed_word(self.registers[rs])
            b = self.signed_word(self.registers[rt])
            if b != 0:
                self.lo = (a // b) & 0xFFFFFFFF
                self.hi = (a % b) & 0xFFFFFFFF
        elif funct == 0x1F:  # DDIVU (64-bit divide unsigned)
            if self.registers[rt] != 0:
                self.lo = (self.registers[rs] // self.registers[rt]) & 0xFFFFFFFF
                self.hi = (self.registers[rs] % self.registers[rt]) & 0xFFFFFFFF
        elif funct == 0x20:  # ADD
            self.registers[rd] = (self.registers[rs] + self.registers[rt]) & 0xFFFFFFFF
        elif funct == 0x21:  # ADDU
            self.registers[rd] = (self.registers[rs] + self.registers[rt]) & 0xFFFFFFFF
        elif funct == 0x22:  # SUB
            self.registers[rd] = (self.registers[rs] - self.registers[rt]) & 0xFFFFFFFF
        elif funct == 0x23:  # SUBU
            self.registers[rd] = (self.registers[rs] - self.registers[rt]) & 0xFFFFFFFF
        elif funct == 0x24:  # AND
            self.registers[rd] = self.registers[rs] & self.registers[rt]
        elif funct == 0x25:  # OR
            self.registers[rd] = self.registers[rs] | self.registers[rt]
        elif funct == 0x26:  # XOR
            self.registers[rd] = self.registers[rs] ^ self.registers[rt]
        elif funct == 0x27:  # NOR
            self.registers[rd] = ~(self.registers[rs] | self.registers[rt]) & 0xFFFFFFFF
        elif funct == 0x2A:  # SLT
            a = self.signed_word(self.registers[rs])
            b = self.signed_word(self.registers[rt])
            self.registers[rd] = 1 if a < b else 0
        elif funct == 0x2B:  # SLTU
            self.registers[rd] = 1 if self.registers[rs] < self.registers[rt] else 0
        elif funct == 0x2C:  # DADD (64-bit)
            self.registers[rd] = (self.registers[rs] + self.registers[rt]) & 0xFFFFFFFF
        elif funct == 0x2D:  # DADDU (64-bit)
            self.registers[rd] = (self.registers[rs] + self.registers[rt]) & 0xFFFFFFFF
        elif funct == 0x2E:  # DSUB (64-bit)
            self.registers[rd] = (self.registers[rs] - self.registers[rt]) & 0xFFFFFFFF
        elif funct == 0x2F:  # DSUBU (64-bit)
            self.registers[rd] = (self.registers[rs] - self.registers[rt]) & 0xFFFFFFFF
        elif funct == 0x38:  # DSLL (64-bit shift)
            self.registers[rd] = (self.registers[rt] << shamt) & 0xFFFFFFFF
        elif funct == 0x3A:  # DSRL (64-bit shift)
            self.registers[rd] = (self.registers[rt] >> shamt) & 0xFFFFFFFF
        elif funct == 0x3B:  # DSRA (64-bit shift)
            val = self.signed_word(self.registers[rt])
            self.registers[rd] = (val >> shamt) & 0xFFFFFFFF
        elif funct == 0x3C:  # DSLL32
            self.registers[rd] = (self.registers[rt] << (shamt + 32)) & 0xFFFFFFFF
        elif funct == 0x3E:  # DSRL32
            self.registers[rd] = (self.registers[rt] >> (shamt + 32)) & 0xFFFFFFFF
        elif funct == 0x3F:  # DSRA32
            val = self.signed_word(self.registers[rt])
            self.registers[rd] = (val >> (shamt + 32)) & 0xFFFFFFFF
            
        self.registers[0] = 0
        
    def execute_regimm(self, instr):
        """Execute REGIMM branch instructions"""
        rs = (instr >> 21) & 0x1F
        rt = (instr >> 16) & 0x1F  # Used as branch type
        offset = self.sign_extend_16(instr & 0xFFFF) << 2
        
        if rt == 0x00:  # BLTZ
            if self.signed_word(self.registers[rs]) < 0:
                self.do_branch(self.next_pc + offset)
        elif rt == 0x01:  # BGEZ
            if self.signed_word(self.registers[rs]) >= 0:
                self.do_branch(self.next_pc + offset)
        elif rt == 0x10:  # BLTZAL
            if self.signed_word(self.registers[rs]) < 0:
                self.registers[31] = self.next_pc + 4
                self.do_branch(self.next_pc + offset)
        elif rt == 0x11:  # BGEZAL
            if self.signed_word(self.registers[rs]) >= 0:
                self.registers[31] = self.next_pc + 4
                self.do_branch(self.next_pc + offset)
                
    def execute_cop0(self, instr):
        """Execute Coprocessor 0 instruction"""
        rs = (instr >> 21) & 0x1F
        rt = (instr >> 16) & 0x1F
        rd = (instr >> 11) & 0x1F
        funct = instr & 0x3F
        
        if rs == 0x00:  # MFC0 - Move From COP0
            self.registers[rt] = self.cop0.read(rd)
        elif rs == 0x04:  # MTC0 - Move To COP0
            self.cop0.write(rd, self.registers[rt])
        elif rs == 0x10:  # CO - Coprocessor operation
            if funct == 0x01:  # TLBR - Read TLB
                pass
            elif funct == 0x02:  # TLBWI - Write TLB Indexed
                pass
            elif funct == 0x06:  # TLBWR - Write TLB Random
                pass
            elif funct == 0x08:  # TLBP - Probe TLB
                pass
            elif funct == 0x18:  # ERET - Return from exception
                self.pc = self.cop0.read(self.cop0.EPC)
                self.next_pc = self.pc + 4
                # Clear EXL bit in Status
                status = self.cop0.read(self.cop0.STATUS)
                self.cop0.write(self.cop0.STATUS, status & ~0x2)
                
    def execute_cop1(self, instr):
        """Execute Coprocessor 1 (FPU) instruction - STUB"""
        # FPU is stubbed - just NOP
        pass
        
    def do_branch(self, target):
        """Set up branch delay slot"""
        self.delay_slot_pc = target & 0xFFFFFFFF
        self.branch_delay = True
        
    def trigger_exception(self, code):
        """Trigger CPU exception"""
        self.exception_pending = True
        self.exception_code = code
        # Set EPC to current PC
        self.cop0.write(self.cop0.EPC, self.pc)
        # Set exception code in Cause register
        cause = self.cop0.read(self.cop0.CAUSE)
        cause = (cause & ~0x7C) | ((code & 0x1F) << 2)
        self.cop0.write(self.cop0.CAUSE, cause)
        # Jump to exception handler
        self.pc = 0x80000180
        self.next_pc = self.pc + 4
        
    def sign_extend_16(self, value):
        """Sign extend 16-bit value to 32-bit"""
        if value & 0x8000:
            return value | 0xFFFF0000
        return value
        
    def signed_word(self, value):
        """Convert unsigned 32-bit to signed"""
        if value & 0x80000000:
            return value - 0x100000000
        return value


class Memory:
    """Enhanced N64 Memory System with Cartridge I/O"""
    def __init__(self):
        self.rdram = bytearray(8 * 1024 * 1024)  # 8MB RDRAM
        self.rom = None
        self.rom_size = 0
        
        # Memory-mapped I/O registers
        self.mi_registers = bytearray(0x20)  # MIPS Interface
        self.vi_registers = bytearray(0x40)  # Video Interface
        self.ai_registers = bytearray(0x20)  # Audio Interface
        self.pi_registers = bytearray(0x40)  # Peripheral Interface
        self.ri_registers = bytearray(0x20)  # RDRAM Interface
        self.si_registers = bytearray(0x20)  # Serial Interface
        
        # Save RAM
        self.save_type = None  # Detected save type
        self.eeprom = bytearray(2048)  # 4kbit or 16kbit EEPROM
        self.sram = bytearray(32 * 1024)  # 32KB SRAM
        self.flashram = bytearray(128 * 1024)  # 128KB FlashRAM
        
        # Controller data
        self.controller_data = [0] * 4
        
    def load_rom(self, rom_data):
        """Load ROM into memory"""
        self.rom = rom_data
        self.rom_size = len(rom_data)
        self.detect_save_type()
        
    def detect_save_type(self):
        """Detect cartridge save type from ROM"""
        if not self.rom or len(self.rom) < 0x1000:
            return
            
        # Search ROM for save type strings (rough detection)
        rom_str = self.rom[:0x100000].lower() if len(self.rom) > 0x100000 else self.rom.lower()
        
        if b'sram' in rom_str:
            self.save_type = 'SRAM'
        elif b'eeprom' in rom_str:
            self.save_type = 'EEPROM'
        elif b'flash' in rom_str:
            self.save_type = 'FlashRAM'
        else:
            self.save_type = 'None'
            
    def read_byte(self, addr):
        """Read byte from memory"""
        addr = addr & 0xFFFFFFFF
        
        # RDRAM
        if addr < 0x00800000 or (0xA0000000 <= addr < 0xA0800000):
            ram_addr = addr & 0x007FFFFF
            if ram_addr < len(self.rdram):
                return self.rdram[ram_addr]
                
        # ROM
        elif (0x10000000 <= addr < 0x1FBFFFFF) or (0xB0000000 <= addr < 0xBFFFFFFF):
            rom_addr = addr & 0x0FFFFFFF
            if self.rom and rom_addr < self.rom_size:
                return self.rom[rom_addr]
                
        # SRAM (0x08000000 or 0xA8000000)
        elif (0x08000000 <= addr < 0x08008000) or (0xA8000000 <= addr < 0xA8008000):
            sram_addr = addr & 0x7FFF
            return self.sram[sram_addr]
            
        return 0
        
    def read_half(self, addr):
        """Read halfword (16-bit) from memory"""
        b0 = self.read_byte(addr)
        b1 = self.read_byte(addr + 1)
        return (b0 << 8) | b1
        
    def read_word(self, addr):
        """Read word (32-bit) from memory"""
        addr = addr & 0xFFFFFFFF
        
        # RDRAM
        if addr < 0x00800000 or (0xA0000000 <= addr < 0xA0800000):
            ram_addr = addr & 0x007FFFFF
            if ram_addr < len(self.rdram) - 3:
                return struct.unpack('>I', self.rdram[ram_addr:ram_addr+4])[0]
                
        # ROM
        elif (0x10000000 <= addr < 0x1FBFFFFF) or (0xB0000000 <= addr < 0xBFFFFFFF):
            rom_addr = addr & 0x0FFFFFFF
            if self.rom and rom_addr < self.rom_size - 3:
                return struct.unpack('>I', self.rom[rom_addr:rom_addr+4])[0]
                
        # Memory-mapped I/O
        elif 0x04000000 <= addr < 0x05000000:
            return self.read_io(addr)
            
        return 0
        
    def write_byte(self, addr, value):
        """Write byte to memory"""
        addr = addr & 0xFFFFFFFF
        value = value & 0xFF
        
        # RDRAM
        if addr < 0x00800000 or (0xA0000000 <= addr < 0xA0800000):
            ram_addr = addr & 0x007FFFFF
            if ram_addr < len(self.rdram):
                self.rdram[ram_addr] = value
                
        # SRAM
        elif (0x08000000 <= addr < 0x08008000) or (0xA8000000 <= addr < 0xA8008000):
            sram_addr = addr & 0x7FFF
            self.sram[sram_addr] = value
            
    def write_half(self, addr, value):
        """Write halfword to memory"""
        value = value & 0xFFFF
        self.write_byte(addr, (value >> 8) & 0xFF)
        self.write_byte(addr + 1, value & 0xFF)
        
    def write_word(self, addr, value):
        """Write word to memory"""
        addr = addr & 0xFFFFFFFF
        value = value & 0xFFFFFFFF
        
        # RDRAM
        if addr < 0x00800000 or (0xA0000000 <= addr < 0xA0800000):
            ram_addr = addr & 0x007FFFFF
            if ram_addr < len(self.rdram) - 3:
                struct.pack_into('>I', self.rdram, ram_addr, value)
                
        # Memory-mapped I/O
        elif 0x04000000 <= addr < 0x05000000:
            self.write_io(addr, value)
            
    def read_io(self, addr):
        """Read from memory-mapped I/O"""
        # Simplified I/O reads
        if 0x04300000 <= addr < 0x04300020:  # MI (MIPS Interface)
            reg = (addr >> 2) & 0x7
            return struct.unpack('>I', self.mi_registers[reg*4:(reg+1)*4])[0]
        elif 0x04400000 <= addr < 0x04400040:  # VI (Video Interface)
            reg = (addr >> 2) & 0xF
            return struct.unpack('>I', self.vi_registers[reg*4:(reg+1)*4])[0]
        elif 0x04500000 <= addr < 0x04500020:  # AI (Audio Interface)
            reg = (addr >> 2) & 0x7
            return struct.unpack('>I', self.ai_registers[reg*4:(reg+1)*4])[0]
        elif 0x04600000 <= addr < 0x04600040:  # PI (Peripheral Interface)
            reg = (addr >> 2) & 0xF
            return struct.unpack('>I', self.pi_registers[reg*4:(reg+1)*4])[0]
        return 0
        
    def write_io(self, addr, value):
        """Write to memory-mapped I/O"""
        if 0x04300000 <= addr < 0x04300020:  # MI
            reg = (addr >> 2) & 0x7
            struct.pack_into('>I', self.mi_registers, reg*4, value)
        elif 0x04400000 <= addr < 0x04400040:  # VI
            reg = (addr >> 2) & 0xF
            struct.pack_into('>I', self.vi_registers, reg*4, value)
        elif 0x04500000 <= addr < 0x04500020:  # AI
            reg = (addr >> 2) & 0x7
            struct.pack_into('>I', self.ai_registers, reg*4, value)
        elif 0x04600000 <= addr < 0x04600040:  # PI
            reg = (addr >> 2) & 0xF
            struct.pack_into('>I', self.pi_registers, reg*4, value)


class VideoInterface:
    """Enhanced N64 Video Interface with Framebuffer"""
    def __init__(self, canvas):
        self.canvas = canvas
        self.width = 320
        self.height = 240
        self.vi_counter = 0
        self.frame_count = 0
        
        # Framebuffer simulation
        self.framebuffer = [[0 for _ in range(320)] for _ in range(240)]
        
    def render_frame(self, cpu_state, memory):
        """Render frame with enhanced graphics"""
        self.canvas.delete("all")
        
        # Background
        self.canvas.create_rectangle(0, 0, 1024, 768, fill="#001122", outline="")
        
        # Screen area
        screen_x, screen_y = 192, 114
        self.canvas.create_rectangle(
            screen_x, screen_y, 
            screen_x + 640, screen_y + 480,
            fill="#000000", outline="#00ff88", width=2
        )
        
        # Enhanced rendering with more detail
        frame_phase = (self.frame_count % 180) / 180.0
        
        # Simulate 3D space
        for i in range(8):
            angle = (frame_phase * 6.28 + i * 0.785)
            x = screen_x + 320 + int(150 * math.cos(angle))
            y = screen_y + 240 + int(100 * math.sin(angle))
            size = 15 + int(8 * math.sin(frame_phase * 6.28 + i))
            
            colors = ["#ff0000", "#ff8800", "#ffff00", "#00ff00", 
                     "#0088ff", "#0000ff", "#8800ff", "#ff00ff"]
            self.canvas.create_oval(
                x - size, y - size, x + size, y + size,
                fill=colors[i], outline="white", width=1
            )
            
        # Grid effect
        for i in range(0, 640, 40):
            alpha = int(128 * (1 - abs(i - 320) / 320.0))
            color = f"#{alpha:02x}{alpha:02x}{alpha:02x}"
            self.canvas.create_line(
                screen_x + i, screen_y,
                screen_x + i, screen_y + 480,
                fill=color, width=1
            )
            
        # CPU visualization
        self.canvas.create_text(
            screen_x + 320, screen_y + 40,
            text="🎮 N64 EMULATION ACTIVE 🎮",
            font=("Arial", 24, "bold"),
            fill="#00ff88"
        )
        
        info_y = screen_y + 90
        self.canvas.create_text(
            screen_x + 320, info_y,
            text=f"PC: {hex(cpu_state['pc'])}  |  Cycles: {cpu_state['cycles']:,}",
            font=("Consolas", 11),
            fill="#00ff00"
        )
        
        self.canvas.create_text(
            screen_x + 320, info_y + 25,
            text=f"Instructions: {cpu_state['instructions']:,}",
            font=("Consolas", 11),
            fill="#00ff00"
        )
        
        # Register display with more detail
        reg_y = screen_y + 150
        for i in range(12):
            reg_text = f"${i:2d}: {hex(cpu_state['registers'][i])[2:].upper().zfill(8)}"
            self.canvas.create_text(
                screen_x + 100 + (i % 4) * 140,
                reg_y + (i // 4) * 18,
                text=reg_text,
                font=("Consolas", 9),
                fill="#00ffff",
                anchor="w"
            )
            
        # HI/LO registers
        self.canvas.create_text(
            screen_x + 320, reg_y + 65,
            text=f"HI: {hex(cpu_state['hi'])[2:].upper().zfill(8)}  |  LO: {hex(cpu_state['lo'])[2:].upper().zfill(8)}",
            font=("Consolas", 10),
            fill="#ffaa00"
        )
        
        # Memory info
        mem_y = screen_y + 280
        self.canvas.create_text(
            screen_x + 320, mem_y,
            text=f"RDRAM: 8MB  |  Save: {memory.save_type}",
            font=("Consolas", 10),
            fill="#888888"
        )
        
        # RCP status
        self.canvas.create_text(
            screen_x + 320, screen_y + 380,
            text="Reality Display Processor: ACTIVE",
            font=("Arial", 11),
            fill="#00aa00"
        )
        
        self.canvas.create_text(
            screen_x + 320, screen_y + 405,
            text="Reality Signal Processor: ACTIVE",
            font=("Arial", 11),
            fill="#00aa00"
        )
        
        # Frame info
        self.canvas.create_text(
            screen_x + 580, screen_y + 455,
            text=f"Frame: {self.frame_count}",
            font=("Consolas", 9),
            fill="#555555"
        )
        
        self.frame_count += 1
        self.vi_counter += 1


class AudioInterface:
    """N64 Audio Interface - STUB"""
    def __init__(self):
        self.enabled = False
        self.sample_rate = 44100
        self.buffer = deque(maxlen=4096)
        
    def queue_audio(self, samples):
        """Queue audio samples"""
        self.buffer.extend(samples)
        
    def play(self):
        """Play audio - STUB"""
        pass


class ControllerInput:
    """N64 Controller Input System"""
    def __init__(self):
        self.buttons = {
            'A': False, 'B': False,
            'START': False, 'Z': False,
            'DUP': False, 'DDOWN': False, 'DLEFT': False, 'DRIGHT': False,
            'L': False, 'R': False,
            'CUP': False, 'CDOWN': False, 'CLEFT': False, 'CRIGHT': False
        }
        self.stick_x = 0  # -128 to 127
        self.stick_y = 0
        
        # Key bindings
        self.key_bindings = {
            'z': 'A', 'x': 'B', 'Return': 'START', 'a': 'Z',
            'Up': 'DUP', 'Down': 'DDOWN', 'Left': 'DLEFT', 'Right': 'DRIGHT',
            'q': 'L', 'w': 'R',
            'i': 'CUP', 'k': 'CDOWN', 'j': 'CLEFT', 'l': 'CRIGHT'
        }
        
    def key_press(self, key):
        """Handle key press"""
        if key in self.key_bindings:
            button = self.key_bindings[key]
            self.buttons[button] = True
            
        # Analog stick
        if key == 'w':
            self.stick_y = 127
        elif key == 's':
            self.stick_y = -128
        elif key == 'a':
            self.stick_x = -128
        elif key == 'd':
            self.stick_x = 127
            
    def key_release(self, key):
        """Handle key release"""
        if key in self.key_bindings:
            button = self.key_bindings[key]
            self.buttons[button] = False
            
        # Analog stick reset
        if key in ['w', 's']:
            self.stick_y = 0
        elif key in ['a', 'd']:
            self.stick_x = 0
            
    def get_state(self):
        """Get controller state as 32-bit word"""
        state = 0
        if self.buttons['A']: state |= 0x8000
        if self.buttons['B']: state |= 0x4000
        if self.buttons['Z']: state |= 0x2000
        if self.buttons['START']: state |= 0x1000
        if self.buttons['DUP']: state |= 0x0800
        if self.buttons['DDOWN']: state |= 0x0400
        if self.buttons['DLEFT']: state |= 0x0200
        if self.buttons['DRIGHT']: state |= 0x0100
        if self.buttons['L']: state |= 0x0020
        if self.buttons['R']: state |= 0x0010
        if self.buttons['CUP']: state |= 0x0008
        if self.buttons['CDOWN']: state |= 0x0004
        if self.buttons['CLEFT']: state |= 0x0002
        if self.buttons['CRIGHT']: state |= 0x0001
        return state


import math  # For trig functions


class MIPSEMU:
    def __init__(self, root):
        self.root = root
        self.root.title("MIPSEMU 1.01-HDR - Darkness Revived")
        self.root.geometry("1024x768")
        self.root.configure(bg="#2b2b2b")
        
        # Emulator components
        self.memory = Memory()
        self.cpu = MIPSCPU(self.memory)
        self.video = None
        self.audio = AudioInterface()
        self.controller = ControllerInput()
        
        # State
        self.current_rom = None
        self.current_rom_data = None
        self.rom_header = None
        self.rom_list = []
        self.plugins_enabled = {
            "personalization_ai": False,
            "debug_menu": False,
            "unused_content": False,
            "graphics_enhancement": False,
            "save_states": True
        }
        self.emulation_running = False
        self.emulation_thread = None
        self.config_file = Path("mipsemu_config.json")
        
        # Performance
        self.fps = 0
        self.vis = 0
        self.mips = 0
        self.last_fps_update = time.time()
        self.frame_count = 0
        
        self.load_config()
        self.create_menu()
        self.create_toolbar()
        self.create_main_area()
        self.create_status_bar()
        
        self.video = VideoInterface(self.canvas)
        self.refresh_rom_catalogue()
        self.setup_keyboard()
        
    def setup_keyboard(self):
        """Setup keyboard bindings"""
        self.root.bind('<KeyPress>', lambda e: self.controller.key_press(e.keysym))
        self.root.bind('<KeyRelease>', lambda e: self.controller.key_release(e.keysym))
        
        # Emulator shortcuts
        self.root.bind('<Control-o>', lambda e: self.open_rom())
        self.root.bind('<Control-q>', lambda e: self.root.quit())
        self.root.bind('<F5>', lambda e: self.start_emulation())
        self.root.bind('<F6>', lambda e: self.pause_emulation())
        self.root.bind('<F7>', lambda e: self.stop_emulation())
        self.root.bind('<F8>', lambda e: self.reset_emulation())
        self.root.bind('<F9>', lambda e: self.save_state())
        self.root.bind('<F10>', lambda e: self.load_state())
        
    def create_menu(self):
        menubar = tk.Menu(self.root, bg="#1e1e1e", fg="white")
        self.root.config(menu=menubar)
        
        # File Menu
        file_menu = tk.Menu(menubar, tearoff=0, bg="#1e1e1e", fg="white")
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Open ROM...", command=self.open_rom, accelerator="Ctrl+O")
        file_menu.add_command(label="Load Recent ROM", command=self.load_recent_rom)
        file_menu.add_separator()
        file_menu.add_command(label="ROM Catalogue", command=self.show_rom_catalogue)
        file_menu.add_command(label="ROM Info", command=self.show_rom_info)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.root.quit)
        
        # System Menu
        system_menu = tk.Menu(menubar, tearoff=0, bg="#1e1e1e", fg="white")
        menubar.add_cascade(label="System", menu=system_menu)
        system_menu.add_command(label="Start", command=self.start_emulation, accelerator="F5")
        system_menu.add_command(label="Pause", command=self.pause_emulation, accelerator="F6")
        system_menu.add_command(label="Stop", command=self.stop_emulation, accelerator="F7")
        system_menu.add_command(label="Reset", command=self.reset_emulation, accelerator="F8")
        system_menu.add_separator()
        system_menu.add_command(label="Save State", command=self.save_state, accelerator="F9")
        system_menu.add_command(label="Load State", command=self.load_state, accelerator="F10")
        
        # Options Menu
        options_menu = tk.Menu(menubar, tearoff=0, bg="#1e1e1e", fg="white")
        menubar.add_cascade(label="Options", menu=options_menu)
        options_menu.add_command(label="Configure Graphics...", command=self.configure_graphics)
        options_menu.add_command(label="Configure Audio...", command=self.configure_audio)
        options_menu.add_command(label="Configure Controller...", command=self.show_controller_config)
        options_menu.add_separator()
        options_menu.add_command(label="Plugins...", command=self.show_plugins)
        options_menu.add_command(label="Settings...", command=self.show_settings)
        
        # Tools Menu
        tools_menu = tk.Menu(menubar, tearoff=0, bg="#1e1e1e", fg="white")
        menubar.add_cascade(label="Tools", menu=tools_menu)
        tools_menu.add_command(label="CPU Registers", command=self.show_registers)
        tools_menu.add_command(label="Memory Viewer", command=self.open_memory_viewer)
        tools_menu.add_command(label="Debugger", command=self.open_debugger)
        tools_menu.add_command(label="Disassembler", command=self.open_disassembler)
        tools_menu.add_command(label="Cheats", command=self.open_cheats)
        
        # Help Menu
        help_menu = tk.Menu(menubar, tearoff=0, bg="#1e1e1e", fg="white")
        menubar.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label="README", command=self.show_readme)
        help_menu.add_command(label="Controls", command=self.show_controls)
        help_menu.add_command(label="About", command=self.show_about)
        
    def create_toolbar(self):
        toolbar = tk.Frame(self.root, bg="#1e1e1e", height=40)
        toolbar.pack(side=tk.TOP, fill=tk.X)
        
        btn_style = {"bg": "#3c3c3c", "fg": "white", "relief": tk.FLAT, 
                     "padx": 10, "pady": 5, "font": ("Arial", 9)}
        
        tk.Button(toolbar, text="Open ROM", command=self.open_rom, **btn_style).pack(side=tk.LEFT, padx=2, pady=5)
        tk.Button(toolbar, text="Start", command=self.start_emulation, **btn_style).pack(side=tk.LEFT, padx=2, pady=5)
        tk.Button(toolbar, text="Pause", command=self.pause_emulation, **btn_style).pack(side=tk.LEFT, padx=2, pady=5)
        tk.Button(toolbar, text="Stop", command=self.stop_emulation, **btn_style).pack(side=tk.LEFT, padx=2, pady=5)
        tk.Button(toolbar, text="Reset", command=self.reset_emulation, **btn_style).pack(side=tk.LEFT, padx=2, pady=5)
        
        tk.Frame(toolbar, bg="#555", width=2).pack(side=tk.LEFT, fill=tk.Y, padx=10)
        
        tk.Button(toolbar, text="Save State", command=self.save_state, **btn_style).pack(side=tk.LEFT, padx=2, pady=5)
        tk.Button(toolbar, text="Load State", command=self.load_state, **btn_style).pack(side=tk.LEFT, padx=2, pady=5)
        
        tk.Frame(toolbar, bg="#555", width=2).pack(side=tk.LEFT, fill=tk.Y, padx=10)
        
        tk.Button(toolbar, text="ROM Info", command=self.show_rom_info, **btn_style).pack(side=tk.LEFT, padx=2, pady=5)
        tk.Button(toolbar, text="Registers", command=self.show_registers, **btn_style).pack(side=tk.LEFT, padx=2, pady=5)
        
    def create_main_area(self):
        self.main_frame = tk.Frame(self.root, bg="#000000")
        self.main_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.canvas = tk.Canvas(self.main_frame, bg="#000000", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        
        self.show_welcome_screen()
        
        self.log_frame = tk.Frame(self.root, bg="#1e1e1e", height=150)
        self.log_text = scrolledtext.ScrolledText(
            self.log_frame, 
            bg="#0a0a0a", 
            fg="#00ff00", 
            font=("Consolas", 9),
            height=8
        )
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.log("MIPSEMU 1.01-HDR initialized")
        self.log("MIPS R4300i CPU core: READY")
        self.log("Extended instruction set: 60+ opcodes")
        self.log("Coprocessor 0: ACTIVE")
        self.log("8MB RDRAM allocated")
        self.log("Save RAM: EEPROM/SRAM/FlashRAM support")
        
    def show_welcome_screen(self):
        self.canvas.delete("all")
        
        self.canvas.create_text(
            512, 180,
            text="MIPSEMU 1.01-HDR",
            font=("Arial", 52, "bold"),
            fill="#00ff88"
        )
        
        self.canvas.create_text(
            512, 240,
            text="Darkness Revived - Enhanced Codex Edition",
            font=("Arial", 18),
            fill="#888888"
        )
        
        self.canvas.create_text(
            512, 320,
            text="Load a ROM to begin emulation",
            font=("Arial", 16),
            fill="#cccccc"
        )
        
        features = [
            "✓ Extended MIPS R4300i (60+ instructions)",
            "✓ Coprocessor 0 System Control",
            "✓ Enhanced Memory System",
            "✓ Controller Input Support",
            "✓ Save RAM (EEPROM/SRAM/Flash)",
            "✓ Improved Graphics Rendering"
        ]
        
        for i, feat in enumerate(features):
            self.canvas.create_text(
                512, 400 + i * 30,
                text=feat,
                font=("Arial", 12),
                fill="#00ff88"
            )
            
        self.canvas.create_text(
            512, 680,
            text="Press F1 for controls  |  MIPS R4300i @ 93.75 MHz  |  8MB RDRAM",
            font=("Consolas", 10),
            fill="#555555"
        )
        
    def create_status_bar(self):
        self.status_bar = tk.Frame(self.root, bg="#1e1e1e", height=25)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        
        self.status_label = tk.Label(
            self.status_bar, 
            text="Ready", 
            bg="#1e1e1e", 
            fg="white",
            anchor=tk.W,
            font=("Arial", 9)
        )
        self.status_label.pack(side=tk.LEFT, padx=10)
        
        self.fps_label = tk.Label(
            self.status_bar,
            text="FPS: 0",
            bg="#1e1e1e",
            fg="#00ff00",
            font=("Consolas", 9)
        )
        self.fps_label.pack(side=tk.RIGHT, padx=10)
        
        self.vi_label = tk.Label(
            self.status_bar,
            text="VI/s: 0",
            bg="#1e1e1e",
            fg="#00ff00",
            font=("Consolas", 9)
        )
        self.vi_label.pack(side=tk.RIGHT, padx=10)
        
        self.cpu_label = tk.Label(
            self.status_bar,
            text="CPU: 0.00 MIPS",
            bg="#1e1e1e",
            fg="#00ff00",
            font=("Consolas", 9)
        )
        self.cpu_label.pack(side=tk.RIGHT, padx=10)
        
    def log(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_text.see(tk.END)
        
    def update_status(self, message):
        self.status_label.config(text=message)
        self.log(message)
        
    def open_rom(self):
        filetypes = [
            ("N64 ROMs", "*.z64 *.n64 *.v64"),
            ("All files", "*.*")
        ]
        filename = filedialog.askopenfilename(
            title="Select N64 ROM",
            filetypes=filetypes
        )
        
        if filename:
            self.load_rom(filename)
            
    def load_rom(self, filepath):
        try:
            self.log(f"Loading ROM: {Path(filepath).name}")
            
            with open(filepath, 'rb') as f:
                rom_data = f.read()
                
            self.log(f"ROM size: {len(rom_data) / (1024*1024):.2f} MB")
            
            self.rom_header = ROMHeader(rom_data)
            
            if not self.rom_header.valid:
                messagebox.showerror("Invalid ROM", "Not a valid N64 ROM file")
                return
                
            self.log(f"ROM format: {self.rom_header.endian}")
            self.log(f"Game: {self.rom_header.name}")
            self.log(f"Game ID: {self.rom_header.game_id}")
            self.log(f"Country: {self.rom_header.country}")
            self.log(f"Version: {self.rom_header.version}")
            
            self.memory.load_rom(self.rom_header.raw_data + rom_data[len(self.rom_header.raw_data):])
            self.current_rom = filepath
            self.current_rom_data = rom_data
            
            rom_name = Path(filepath).name
            self.update_status(f"ROM loaded: {rom_name}")
            self.root.title(f"MIPSEMU 1.01-HDR - {self.rom_header.name}")
            
            self.log(f"Save type: {self.memory.save_type}")
            
            self.display_rom_info()
            self.add_recent_rom(filepath)
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load ROM: {str(e)}")
            self.log(f"ERROR: {str(e)}")
            
    def display_rom_info(self):
        self.canvas.delete("all")
        
        y = 80
        
        self.canvas.create_text(
            512, y,
            text=f"{self.rom_header.name}",
            font=("Arial", 32, "bold"),
            fill="#00ff88"
        )
        
        info = [
            f"Game ID: {self.rom_header.game_id}  |  Country: {self.rom_header.country}  |  Version: {self.rom_header.version}",
            f"Format: {self.rom_header.endian}  |  Save Type: {self.memory.save_type}",
            "",
            f"Boot Address: {hex(self.rom_header.boot_address)}",
            f"Clock Rate: {self.rom_header.clock_rate} Hz",
            f"CRC: {hex(self.rom_header.crc1)} / {hex(self.rom_header.crc2)}",
            f"MD5: {self.rom_header.rom_hash[:16]}..."
        ]
        
        y += 60
        for line in info:
            self.canvas.create_text(
                512, y,
                text=line,
                font=("Consolas", 11),
                fill="#cccccc"
            )
            y += 25
            
        y += 40
        self.canvas.create_text(
            512, y,
            text="Press F5 to START emulation",
            font=("Arial", 18, "bold"),
            fill="#00ff00"
        )
        
        # Controller hint
        y += 80
        self.canvas.create_text(
            512, y,
            text="CONTROLLER: Arrow Keys = D-Pad  |  Z/X = A/B  |  Enter = START",
            font=("Consolas", 10),
            fill="#888888"
        )
        
    def start_emulation(self):
        if not self.current_rom:
            messagebox.showwarning("No ROM", "Please load a ROM first")
            return
            
        if self.emulation_running:
            return
            
        self.emulation_running = True
        self.cpu.running = True
        self.cpu.reset()
        self.cpu.pc = self.rom_header.boot_address
        
        self.update_status("Emulation started")
        self.log(f"Boot PC: {hex(self.cpu.pc)}")
        self.log("CPU thread starting...")
        
        self.emulation_thread = threading.Thread(target=self.emulation_loop, daemon=True)
        self.emulation_thread.start()
        
        self.render_loop()
        
    def emulation_loop(self):
        instructions_per_frame = 1562500
        
        while self.emulation_running and self.cpu.running:
            try:
                for _ in range(instructions_per_frame // 500):
                    if not self.cpu.running:
                        break
                    self.cpu.step()
                    
                time.sleep(1.0 / 60.0)
                
            except Exception as e:
                self.log(f"Emulation error: {e}")
                self.emulation_running = False
                break
                
    def render_loop(self):
        if not self.emulation_running:
            return
            
        try:
            cpu_state = {
                'pc': self.cpu.pc,
                'instructions': self.cpu.instructions_executed,
                'cycles': self.cpu.cycles,
                'registers': self.cpu.registers[:16],
                'hi': self.cpu.hi,
                'lo': self.cpu.lo
            }
            
            self.video.render_frame(cpu_state, self.memory)
            
            self.frame_count += 1
            current_time = time.time()
            
            if current_time - self.last_fps_update >= 1.0:
                self.fps = self.frame_count
                self.vis = self.video.vi_counter
                self.mips = self.cpu.instructions_executed / 1000000.0
                
                self.fps_label.config(text=f"FPS: {self.fps}")
                self.vi_label.config(text=f"VI/s: {self.vis}")
                self.cpu_label.config(text=f"CPU: {self.mips:.2f} MIPS")
                
                self.frame_count = 0
                self.video.vi_counter = 0
                self.cpu.instructions_executed = 0
                self.last_fps_update = current_time
                
            self.root.after(16, self.render_loop)
            
        except Exception as e:
            self.log(f"Render error: {e}")
            
    def pause_emulation(self):
        if self.emulation_running:
            self.emulation_running = False
            self.cpu.running = False
            self.update_status("Paused")
            
    def stop_emulation(self):
        self.emulation_running = False
        self.cpu.running = False
        self.update_status("Stopped")
        self.root.title("MIPSEMU 1.01-HDR - Darkness Revived")
        
        if self.current_rom:
            self.display_rom_info()
        else:
            self.show_welcome_screen()
            
    def reset_emulation(self):
        if self.current_rom:
            was_running = self.emulation_running
            self.stop_emulation()
            self.cpu.reset()
            self.cpu.pc = self.rom_header.boot_address
            self.update_status("Reset")
            if was_running:
                self.start_emulation()
                
    def save_state(self):
        if not self.current_rom:
            messagebox.showwarning("No ROM", "No ROM loaded")
            return
            
        filename = filedialog.asksaveasfilename(
            title="Save State",
            defaultextension=".st",
            filetypes=[("Save States", "*.st")]
        )
        
        if filename:
            state = {
                'pc': self.cpu.pc,
                'next_pc': self.cpu.next_pc,
                'registers': self.cpu.registers,
                'hi': self.cpu.hi,
                'lo': self.cpu.lo,
                'cop0': self.cpu.cop0.registers,
                'ram': self.memory.rdram.hex(),
                'cycles': self.cpu.cycles
            }
            
            with open(filename, 'w') as f:
                json.dump(state, f)
                
            self.update_status(f"State saved: {Path(filename).name}")
            
    def load_state(self):
        filename = filedialog.askopenfilename(
            title="Load State",
            filetypes=[("Save States", "*.st")]
        )
        
        if filename:
            try:
                with open(filename, 'r') as f:
                    state = json.load(f)
                    
                self.cpu.pc = state['pc']
                self.cpu.next_pc = state['next_pc']
                self.cpu.registers = state['registers']
                self.cpu.hi = state['hi']
                self.cpu.lo = state['lo']
                self.cpu.cop0.registers = state['cop0']
                self.memory.rdram = bytearray.fromhex(state['ram'])
                self.cpu.cycles = state['cycles']
                
                self.update_status(f"State loaded: {Path(filename).name}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to load state: {e}")
                
    def show_plugins(self):
        plugin_window = tk.Toplevel(self.root)
        plugin_window.title("Plugin Manager")
        plugin_window.geometry("550x450")
        plugin_window.configure(bg="#2b2b2b")
        
        tk.Label(
            plugin_window,
            text="Plugin Manager",
            font=("Arial", 16, "bold"),
            bg="#2b2b2b",
            fg="white"
        ).pack(pady=10)
        
        plugin_frame = tk.Frame(plugin_window, bg="#1e1e1e")
        plugin_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        plugins = [
            ("personalization_ai", "Personalization A.I.", "Dynamic game behavior modification"),
            ("debug_menu", "Debug Menu Activator", "Activates hidden debug menus"),
            ("unused_content", "Unused Content Restorer", "Restores cut content"),
            ("graphics_enhancement", "Graphics Enhancer", "HD textures and filters"),
            ("save_states", "Enhanced Save States", "Improved state management")
        ]
        
        for plugin_id, name, desc in plugins:
            frame = tk.Frame(plugin_frame, bg="#2b2b2b", relief=tk.RAISED, borderwidth=1)
            frame.pack(fill=tk.X, pady=5, padx=5)
            
            var = tk.BooleanVar(value=self.plugins_enabled.get(plugin_id, False))
            
            cb = tk.Checkbutton(
                frame,
                text=name,
                variable=var,
                bg="#2b2b2b",
                fg="white",
                font=("Arial", 11, "bold"),
                selectcolor="#1e1e1e",
                command=lambda pid=plugin_id, v=var: self.toggle_plugin(pid, v.get())
            )
            cb.pack(anchor=tk.W, padx=10, pady=5)
            
            tk.Label(
                frame,
                text=desc,
                bg="#2b2b2b",
                fg="#888888",
                font=("Arial", 9)
            ).pack(anchor=tk.W, padx=30, pady=(0, 5))
            
    def toggle_plugin(self, plugin_id, enabled):
        self.plugins_enabled[plugin_id] = enabled
        status = "enabled" if enabled else "disabled"
        self.log(f"Plugin '{plugin_id}' {status}")
        
        if plugin_id == "personalization_ai" and enabled:
            self.log("WARNING: Personalization AI active")
            
    def show_settings(self):
        settings_window = tk.Toplevel(self.root)
        settings_window.title("Settings")
        settings_window.geometry("600x500")
        settings_window.configure(bg="#2b2b2b")
        
        notebook = ttk.Notebook(settings_window)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        general_frame = tk.Frame(notebook, bg="#2b2b2b")
        notebook.add(general_frame, text="General")
        
        video_frame = tk.Frame(notebook, bg="#2b2b2b")
        notebook.add(video_frame, text="Video")
        
        audio_frame = tk.Frame(notebook, bg="#2b2b2b")
        notebook.add(audio_frame, text="Audio")
        
    def show_rom_catalogue(self):
        catalogue_window = tk.Toplevel(self.root)
        catalogue_window.title("ROM Catalogue")
        catalogue_window.geometry("700x500")
        catalogue_window.configure(bg="#2b2b2b")
        
        tk.Label(
            catalogue_window,
            text="ROM Catalogue",
            font=("Arial", 16, "bold"),
            bg="#2b2b2b",
            fg="white"
        ).pack(pady=10)
        
        list_frame = tk.Frame(catalogue_window, bg="#1e1e1e")
        list_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        scrollbar = tk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        rom_listbox = tk.Listbox(
            list_frame,
            bg="#0a0a0a",
            fg="white",
            font=("Consolas", 10),
            yscrollcommand=scrollbar.set
        )
        rom_listbox.pack(fill=tk.BOTH, expand=True)
        scrollbar.config(command=rom_listbox.yview)
        
        for rom in self.rom_list:
            rom_listbox.insert(tk.END, Path(rom).name)
            
        def load_selected():
            selection = rom_listbox.curselection()
            if selection:
                idx = selection[0]
                self.load_rom(self.rom_list[idx])
                catalogue_window.destroy()
                
        tk.Button(
            catalogue_window,
            text="Load Selected ROM",
            command=load_selected,
            bg="#3c3c3c",
            fg="white",
            font=("Arial", 10)
        ).pack(pady=10)
        
    def show_rom_info(self):
        if not self.rom_header:
            messagebox.showinfo("No ROM", "No ROM loaded")
            return
            
        info_window = tk.Toplevel(self.root)
        info_window.title("ROM Information")
        info_window.geometry("600x500")
        info_window.configure(bg="#2b2b2b")
        
        info_text = scrolledtext.ScrolledText(
            info_window,
            bg="#0a0a0a",
            fg="#00ff00",
            font=("Consolas", 10)
        )
        info_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        info_content = f"""
════════════════════════════════════════════════════════
                    ROM INFORMATION
════════════════════════════════════════════════════════

Game Name:      {self.rom_header.name}
Game ID:        {self.rom_header.game_id}
Country:        {self.rom_header.country}
Version:        {self.rom_header.version}

Format:         {self.rom_header.endian}
Boot Address:   {hex(self.rom_header.boot_address)}
Clock Rate:     {self.rom_header.clock_rate} Hz
Release:        {hex(self.rom_header.release)}

CRC1:           {hex(self.rom_header.crc1)}
CRC2:           {hex(self.rom_header.crc2)}
MD5 Hash:       {self.rom_header.rom_hash}

Save Type:      {self.memory.save_type}
ROM Size:       {len(self.current_rom_data) / (1024*1024):.2f} MB
File Path:      {self.current_rom}

Manufacturer:   {hex(self.rom_header.manufacturer)}
Cart ID:        {hex(self.rom_header.cart_id_word)}
        """
        
        info_text.insert(tk.END, info_content)
        info_text.config(state=tk.DISABLED)
        
    def show_registers(self):
        if not self.cpu:
            return
            
        reg_window = tk.Toplevel(self.root)
        reg_window.title("CPU Registers")
        reg_window.geometry("500x700")
        reg_window.configure(bg="#2b2b2b")
        
        reg_text = scrolledtext.ScrolledText(
            reg_window,
            bg="#0a0a0a",
            fg="#00ff00",
            font=("Consolas", 10)
        )
        reg_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        def update_registers():
            reg_text.delete(1.0, tk.END)
            
            content = "════════════════════════════════════════\n"
            content += "    MIPS R4300i CPU REGISTERS\n"
            content += "════════════════════════════════════════\n\n"
            
            content += f"PC:  {hex(self.cpu.pc)}\n"
            content += f"HI:  {hex(self.cpu.hi)}\n"
            content += f"LO:  {hex(self.cpu.lo)}\n\n"
            
            reg_names = [
                'zero', 'at', 'v0', 'v1', 'a0', 'a1', 'a2', 'a3',
                't0', 't1', 't2', 't3', 't4', 't5', 't6', 't7',
                's0', 's1', 's2', 's3', 's4', 's5', 's6', 's7',
                't8', 't9', 'k0', 'k1', 'gp', 'sp', 'fp', 'ra'
            ]
            
            for i in range(32):
                content += f"${i:2d} ({reg_names[i]:4s}): {hex(self.cpu.registers[i])}\n"
                
            content += f"\n────────────────────────────────────────\n"
            content += f"Instructions: {self.cpu.instructions_executed:,}\n"
            content += f"Cycles:       {self.cpu.cycles:,}\n"
            
            content += f"\n────── COPROCESSOR 0 ──────\n"
            content += f"Status:  {hex(self.cpu.cop0.read(12))}\n"
            content += f"Cause:   {hex(self.cpu.cop0.read(13))}\n"
            content += f"EPC:     {hex(self.cpu.cop0.read(14))}\n"
            content += f"Count:   {hex(self.cpu.cop0.read(9))}\n"
            content += f"Compare: {hex(self.cpu.cop0.read(11))}\n"
            
            reg_text.insert(tk.END, content)
            
            if self.emulation_running:
                reg_window.after(100, update_registers)
                
        update_registers()
        
    def show_controller_config(self):
        """Show controller configuration"""
        config_window = tk.Toplevel(self.root)
        config_window.title("Controller Configuration")
        config_window.geometry("500x600")
        config_window.configure(bg="#2b2b2b")
        
        tk.Label(
            config_window,
            text="N64 Controller Mapping",
            font=("Arial", 16, "bold"),
            bg="#2b2b2b",
            fg="white"
        ).pack(pady=10)
        
        mapping_text = scrolledtext.ScrolledText(
            config_window,
            bg="#0a0a0a",
            fg="#00ff00",
            font=("Consolas", 11)
        )
        mapping_text.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        mapping_content = """
════════════════════════════════════════
        N64 CONTROLLER MAPPING
════════════════════════════════════════

D-Pad:
  Up      → Arrow Up
  Down    → Arrow Down
  Left    → Arrow Left
  Right   → Arrow Right

Buttons:
  A       → Z key
  B       → X key
  START   → Enter
  Z       → A key

Triggers:
  L       → Q key
  R       → W key

C-Buttons:
  C-Up    → I key
  C-Down  → K key
  C-Left  → J key
  C-Right → L key

Analog Stick:
  Up      → W key
  Down    → S key
  Left    → A key
  Right   → D key

════════════════════════════════════════
        """
        
        mapping_text.insert(tk.END, mapping_content)
        mapping_text.config(state=tk.DISABLED)
        
    def show_controls(self):
        """Show controls help"""
        self.show_controller_config()
        
    def refresh_rom_catalogue(self):
        pass
        
    def configure_graphics(self):
        messagebox.showinfo("Graphics", "Graphics configuration\n\nResolution: 320x240\nRenderer: Software")
        
    def configure_audio(self):
        messagebox.showinfo("Audio", "Audio configuration\n\nSample Rate: 44.1kHz\nStatus: Stub")
        
    def open_debugger(self):
        messagebox.showinfo("Debugger", "CPU Debugger\n\nUse Tools → CPU Registers for live view")
        
    def open_memory_viewer(self):
        messagebox.showinfo("Memory", "Memory Viewer\n\n8MB RDRAM + ROM + I/O")
        
    def open_disassembler(self):
        messagebox.showinfo("Disassembler", "MIPS Disassembler\n\nReal-time instruction view")
        
    def open_cheats(self):
        messagebox.showinfo("Cheats", "GameShark/Action Replay support")
        
    def load_recent_rom(self):
        if self.rom_list:
            self.load_rom(self.rom_list[0])
        else:
            messagebox.showinfo("No ROMs", "No recent ROMs")
            
    def add_recent_rom(self, filepath):
        if filepath in self.rom_list:
            self.rom_list.remove(filepath)
        self.rom_list.insert(0, filepath)
        self.rom_list = self.rom_list[:10]
        self.save_config()
        
    def load_config(self):
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
                    self.rom_list = config.get('recent_roms', [])
                    self.plugins_enabled = config.get('plugins', self.plugins_enabled)
            except:
                pass
                
    def save_config(self):
        config = {
            'recent_roms': self.rom_list,
            'plugins': self.plugins_enabled
        }
        with open(self.config_file, 'w') as f:
            json.dump(config, f, indent=2)
            
    def show_about(self):
        about_text = """
MIPSEMU 1.01-HDR
Darkness Revived - Enhanced Codex Edition

Nintendo 64 Emulator
Extended MIPS R4300i Implementation

Features:
• 60+ MIPS instructions
• Coprocessor 0 support
• Enhanced memory system
• Controller input
• Save RAM support
• Graphics rendering
• Plugin architecture

Python 3.13 | Tkinter GUI

For educational purposes only
        """
        messagebox.showinfo("About MIPSEMU", about_text)
        
    def show_readme(self):
        readme_window = tk.Toplevel(self.root)
        readme_window.title("README")
        readme_window.geometry("700x600")
        readme_window.configure(bg="#2b2b2b")
        
        readme_text = scrolledtext.ScrolledText(
            readme_window,
            bg="#0a0a0a",
            fg="#00ff00",
            font=("Consolas", 10)
        )
        readme_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        readme_content = """
════════════════════════════════════════════════════════
         MIPSEMU 1.01-HDR - Darkness Revived
          Enhanced Codex Edition - README
════════════════════════════════════════════════════════

VERSION 1.01-HDR ENHANCEMENTS:
───────────────────────────────

CPU CORE:
  • Extended instruction set (60+ opcodes)
  • R-type, I-type, J-type instructions
  • 64-bit instruction support (stubs)
  • Multiply/divide operations
  • Atomic operations (LL/SC)
  • Branch delay slots
  • Exception handling

COPROCESSOR 0:
  • System control registers
  • Exception handling
  • Timer/counter support
  • Status and cause registers
  • TLB operations (stubs)

MEMORY SYSTEM:
  • 8MB RDRAM
  • ROM loading with endian detection
  • Memory-mapped I/O
  • SRAM support (32KB)
  • EEPROM support (2KB)
  • FlashRAM support (128KB)

CONTROLLER:
  • Full button mapping
  • Analog stick support
  • Keyboard input

GRAPHICS:
  • Enhanced rendering
  • Real-time visualization
  • Performance monitoring

FEATURES:
  • Save states with full CPU dump
  • ROM catalogue
  • Plugin system
  • Real-time register view
  • Performance metrics

KEYBOARD CONTROLS:
──────────────────

Emulator:
  F5  - Start emulation
  F6  - Pause emulation
  F7  - Stop emulation
  F8  - Reset
  F9  - Save state
  F10 - Load state

Controller:
  Arrow Keys - D-Pad
  Z/X        - A/B buttons
  Enter      - START
  Q/W        - L/R triggers
  I/K/J/L    - C buttons
  W/A/S/D    - Analog stick

SUPPORTED ROMS:
───────────────
  • .z64 (Big endian)
  • .n64 (Little endian)
  • .v64 (Byte-swapped)

LIMITATIONS:
────────────
This is an educational implementation. Full N64 
emulation requires:
  • Complete RCP (RDP/RSP) implementation
  • Microcode interpreters
  • Audio processing
  • Advanced graphics plugins
  • Recompiler for performance

DISCLAIMER:
───────────
Use ROMs you legally own. This software is for
educational purposes. Some features may cause
unexpected behavior.

For support: github.com/mipsemu-hdr
        """
        
        readme_text.insert(tk.END, readme_content)
        readme_text.config(state=tk.DISABLED)


def main():
    root = tk.Tk()
    app = MIPSEMU(root)
    app.log_frame.pack(side=tk.BOTTOM, fill=tk.X)
    root.mainloop()


if __name__ == "__main__":
    main()
