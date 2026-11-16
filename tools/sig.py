import struct, sys
class Dol:
    def __init__(s, p):
        s.d = open(p,'rb').read(); f=lambda t,i: struct.unpack('>I', s.d[t+4*i:t+4*i+4])[0]
        s.secs=[(f(0,i),f(0x48,i),f(0x90,i)) for i in range(18) if f(0x90,i)]
        s.text=[x for x in s.secs if x[1] < 0x80180000 and x[1] >= 0x80004000][:2]
    def w(s,a):
        for o,b,n in s.secs:
            if b<=a<b+n: return struct.unpack('>I',s.d[o+a-b:o+a-b+4])[0]
        raise KeyError(hex(a))
    def words(s):
        for o,b,n in s.secs:
            if n and b in (0x80004000,0x80006fc0):
                for i in range(0,n,4): yield b+i, struct.unpack('>I',s.d[o+i:o+i+4])[0]
def mask(w):
    op=w>>26
    if op in (18,): return w & 0xFC000003
    if op==16: return w & 0xFFFF0003
    if op in (14,15,24,25,28,29,10,11,12,13,7,8): return w & 0xFFFF0000   # addi/addis/ori/oris/andi/cmpi/mulli/subfic: immediates
    if op in (32,33,34,35,36,37,38,39,40,41,42,43,44,45,46,47,48,49,50,51,52,53,54,55):
        ra=(w>>16)&31
        if ra in (2,13): return w & 0xFFFF0000
    return w
def find(ref, new, addr, before=8, after=8):
    pat=[mask(ref.w(addr+4*k)) for k in range(-before,after+1)]
    ws=list(new.words()) if not hasattr(new,'_ws') else new._ws
    new._ws=ws
    hits=[]
    n=len(pat)
    for i in range(len(ws)-n):
        if all(mask(ws[i+k][1])==pat[k] for k in range(n)):
            hits.append(ws[i+before][0])
    return hits
