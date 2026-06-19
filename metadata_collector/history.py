import json
from .audio_tags import NON_WRITABLE_FIELDS, format_genres_for_tag
from .models import BookSnapshot, ChangeGroup, MetadataChange
from .utils import json_dumps, stringify

def store_snapshot(session, book, source_type='scan'):
    snap=BookSnapshot(book_key=book.key,path=book.path,is_folder_book=book.is_folder_book,source_type=source_type,metadata_json=json_dumps([f.to_dict() for f in book.files]))
    session.add(snap); session.commit(); return snap

def create_change_group(session, book_key, source_type, description=None):
    group=ChangeGroup(book_key=book_key,source_type=source_type,description=description); session.add(group); session.flush(); return group

def metadata_diff(current, selected):
    normalized_selected = dict(selected)
    if 'genres' in normalized_selected:
        normalized_selected['genres'] = format_genres_for_tag(normalized_selected['genres'])
    return {k:v for k,v in normalized_selected.items() if k not in NON_WRITABLE_FIELDS and v not in (None, []) and (format_genres_for_tag(getattr(current,k,None)) if k == 'genres' else getattr(current,k,None))!=v}

def log_changes(session, group, book_key, file_path, changes, source_type, status='success', error_message=None):
    rows=[]
    for tag,(old,new) in changes.items():
        row=MetadataChange(change_group_id=group.id,book_key=book_key,file_path=file_path,tag_name=tag,old_value=stringify(format_genres_for_tag(old) if tag == 'genres' else old),new_value=stringify(format_genres_for_tag(new) if tag == 'genres' else new),source_type=source_type,status=status,error_message=error_message)
        session.add(row); rows.append(row)
    session.flush(); return rows

def selectable_restore_values(snapshot: BookSnapshot, selected_tags: list[str], file_path: str|None=None):
    data=json.loads(snapshot.metadata_json)
    if file_path: data=[d for d in data if d.get('path')==file_path]
    out={}
    for item in data:
        out[item['path']]={tag:item.get(tag) for tag in selected_tags if tag in item}
    return out

def history_for_book(session, book_key):
    return {'snapshots':session.query(BookSnapshot).filter_by(book_key=book_key).order_by(BookSnapshot.created_at.desc()).all(), 'change_groups':session.query(ChangeGroup).filter_by(book_key=book_key).order_by(ChangeGroup.created_at.desc()).all()}
