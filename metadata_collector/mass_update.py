import os, re
SUPPORTED_TARGETS={'title','album','track','disc','narrator','series','description','author','asin'}
def _value(meta, name):
    if name=='filename': return os.path.splitext(os.path.basename(meta.path))[0]
    if name=='folder': return os.path.basename(os.path.dirname(meta.path))
    if name=='series_part': name='series_sequence'
    return getattr(meta, name, None)
def format_pattern(pattern: str, meta) -> str:
    def repl(m):
        key,width=m.group(1),m.group(2)
        val=_value(meta,key)
        if val is None: val=''
        if width:
            try: return f'{int(val):0{int(width)}d}'
            except Exception: return str(val)
        return str(val)
    return re.sub(r'%([a-z_]+)(?::0(\d+))?%', repl, pattern)
def preview_mass_update(files, target_tag: str, pattern: str):
    if target_tag not in SUPPORTED_TARGETS: raise ValueError(f'Unsupported target tag: {target_tag}')
    return [{'path':f.path,'old_value':getattr(f,target_tag,None),'new_value':format_pattern(pattern,f)} for f in files]
