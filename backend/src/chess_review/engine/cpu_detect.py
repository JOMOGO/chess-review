"""Detect CPU instruction set features via CPUID on Windows x64."""

import ctypes
import logging
import struct
import sys

logger = logging.getLogger(__name__)

# x86-64 Windows shellcode: void cpuid_func(uint32_t eax_in, uint32_t ecx_in, uint32_t* out)
# Calling convention: RCX=eax_in, RDX=ecx_in, R8=out pointer
_CPUID_CODE = bytes([
    0x53,                          # push rbx
    0x89, 0xC8,                    # mov eax, ecx
    0x89, 0xD1,                    # mov ecx, edx
    0x0F, 0xA2,                    # cpuid
    0x41, 0x89, 0x00,              # mov [r8], eax
    0x41, 0x89, 0x58, 0x04,        # mov [r8+4], ebx
    0x41, 0x89, 0x48, 0x08,        # mov [r8+8], ecx
    0x41, 0x89, 0x50, 0x0C,        # mov [r8+12], edx
    0x5B,                          # pop rbx
    0xC3,                          # ret
])

MEM_COMMIT = 0x1000
MEM_RESERVE = 0x2000
PAGE_EXECUTE_READWRITE = 0x40
MEM_RELEASE = 0x8000


def _cpuid(eax_in: int, ecx_in: int = 0) -> tuple[int, int, int, int]:
    """Execute CPUID and return (eax, ebx, ecx, edx)."""
    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]

    # Set proper return/arg types for 64-bit pointers
    kernel32.VirtualAlloc.restype = ctypes.c_void_p
    kernel32.VirtualAlloc.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint32, ctypes.c_uint32]
    kernel32.VirtualFree.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint32]

    # Allocate executable memory
    addr = kernel32.VirtualAlloc(None, len(_CPUID_CODE), MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE)
    if not addr:
        raise OSError("VirtualAlloc failed")

    try:
        ctypes.memmove(addr, _CPUID_CODE, len(_CPUID_CODE))

        func_type = ctypes.CFUNCTYPE(None, ctypes.c_uint32, ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint32))
        func = func_type(addr)

        out = (ctypes.c_uint32 * 4)()
        func(eax_in, ecx_in, out)
        return out[0], out[1], out[2], out[3]
    finally:
        kernel32.VirtualFree(addr, 0, MEM_RELEASE)


# Ordered from fastest to slowest / most compatible
STOCKFISH_TIERS = [
    "avx512icl",
    "avx512",
    "avxvnni",
    "bmi2",
    "avx2",
    "sse41-popcnt",
    "x86-64",
]


def detect_best_tier() -> str:
    """Detect the best Stockfish build tier for this CPU.

    Returns one of the tier strings from STOCKFISH_TIERS.
    """
    if sys.platform != "win32":
        logger.warning("CPU detection only implemented for Windows x64, defaulting to x86-64")
        return "x86-64"

    try:
        # CPUID leaf 1: basic feature flags
        _, _, ecx1, _ = _cpuid(1)
        has_sse41 = bool(ecx1 & (1 << 19))
        has_popcnt = bool(ecx1 & (1 << 23))
        has_osxsave = bool(ecx1 & (1 << 27))

        # CPUID leaf 7, sub-leaf 0: extended features
        _, ebx7, ecx7, _ = _cpuid(7, 0)
        has_avx2 = bool(ebx7 & (1 << 5))
        has_bmi2 = bool(ebx7 & (1 << 8))
        has_avx512f = bool(ebx7 & (1 << 16))
        has_avx512dq = bool(ebx7 & (1 << 17))
        has_avx512bw = bool(ebx7 & (1 << 30))
        has_avx512vl = bool(ebx7 & (1 << 31))
        has_avx512vnni = bool(ecx7 & (1 << 11))
        has_avxvnni = bool(ecx7 & (1 << 4))  # AVX-VNNI (not 512)

        # CPUID leaf 7, sub-leaf 1: more features (ICL detection)
        try:
            _, _, ecx7_1, _ = _cpuid(7, 1)
            has_avx512_bf16 = bool(ecx7_1 & (1 << 5))  # proxy for ICL
        except Exception:
            has_avx512_bf16 = False

        logger.info(
            "CPU features: SSE4.1=%s POPCNT=%s AVX2=%s BMI2=%s AVX512F=%s VNNI=%s AVXVNNI=%s",
            has_sse41, has_popcnt, has_avx2, has_bmi2, has_avx512f, has_avx512vnni, has_avxvnni,
        )

        if not has_osxsave:
            # OS doesn't support XSAVE — can't use AVX/AVX2/AVX512
            if has_sse41 and has_popcnt:
                return "sse41-popcnt"
            return "x86-64"

        # AVX-512 tiers
        if has_avx512f and has_avx512dq and has_avx512bw and has_avx512vl:
            if has_avx512vnni and has_avx512_bf16:
                tier = "avx512icl"
            elif has_avx512vnni:
                tier = "vnni512"
            else:
                tier = "avx512"
            logger.info("Detected AVX-512 capable CPU -> %s", tier)
            return tier

        # AVX-VNNI (Alder Lake+)
        if has_avx2 and has_avxvnni:
            logger.info("Detected AVX-VNNI capable CPU -> avxvnni")
            return "avxvnni"

        # BMI2 + AVX2 (Haswell+, Zen3+)
        if has_avx2 and has_bmi2:
            logger.info("Detected BMI2+AVX2 capable CPU -> bmi2")
            return "bmi2"

        # AVX2 only (Zen1/Zen2 where BMI2 was slow)
        if has_avx2:
            logger.info("Detected AVX2 capable CPU -> avx2")
            return "avx2"

        # SSE4.1 + POPCNT
        if has_sse41 and has_popcnt:
            logger.info("Detected SSE4.1+POPCNT capable CPU -> sse41-popcnt")
            return "sse41-popcnt"

        logger.info("No advanced features detected -> x86-64")
        return "x86-64"

    except Exception:
        logger.exception("CPUID detection failed, defaulting to x86-64")
        return "x86-64"
