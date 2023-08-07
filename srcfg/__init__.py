import re
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Union, List, Tuple, Optional, Dict, Sequence, Callable, TypeVar
import json

COMMENT_PREFIX = ";;"

T = TypeVar("T")

@dataclass
class SrcfgFile:
    _sections: Dict[str, Union["SrcfgSection", List["SrcfgSection"]]] = field(default_factory=lambda: {})

    def __iter__(self):
        yield from self._sections

    def __getitem__(self, section_name: str):
        return self._sections[section_name]
    
    def __contains__(self, section_name: str):
        return section_name in self._sections
    
    #####

    def has_section(self, section_name: str):
        return section_name in self._sections
    
    def get_section(self, section_name: str) -> "SrcfgSection":
        section = self._sections[section_name]
        if not isinstance(section, SrcfgSection):
            raise ValueError("Unexpected section list")
        return section
    
    def get_section_list(self, section_name: str) -> Sequence["SrcfgSection"]:
        section = self._sections[section_name]
        if isinstance(section, SrcfgSection):
            raise ValueError("Unexpected section (expected a list)")
        return section

    #####
    
    def _add_section(
        self,
        section_name: str,
        current_section: Optional["SrcfgSection"],
        ref_section: Optional["SrcfgSection"],
        is_array: bool
    ) -> Union[Tuple["SrcfgSection", None], Tuple[None, str]]:
        if section_name.startswith("."):
            if not current_section:
                return None, "Cannot use dot-section names outside a section"
            ref_section = current_section._get_top_section()
            # remove the dot from the name
            section_name = section_name[1:]

        if ref_section:
            print("LOOK FOR SECTION", section_name, "IN", ref_section.name)
        else:
            print("LOOK FOR SECTION", section_name)
        
        # the reference section is the file if none is specified
        _ref_section = ref_section if ref_section else self

        # separate the name of the section
        # - "a.b.c" becomes ["a", "b.c"]
        # - "a" becomes ["a"]
        section_name_parts = section_name.split(".", maxsplit=1)
        if not section_name_parts:
            # This should not happen: the name of the section is empty
            # (or it was only ".")
            return None, "Unable to parse section name"
        elif len(section_name_parts) == 1:
            # The name has no dot: we reached the end
            if is_array:
                section = SrcfgSection(section_name, _ref_section)
                if section_name in _ref_section._sections:
                    section_array = _ref_section._sections[section_name]
                    if isinstance(section_array, SrcfgSection):
                        return None, f"Section with name {section_name} is not an array"
                    section_array.append(section)
                    return section, None
                else:
                    _ref_section._sections[section_name] = [section]
                    return section, None
            else:
                if section_name in _ref_section._sections:
                    section = _ref_section._sections[section_name]
                    if not isinstance(section, SrcfgSection):
                        return None, f"Section with name {section_name} is an array"
                    return section, None
                else:
                    section = SrcfgSection(section_name, _ref_section)
                    _ref_section._sections[section_name] = section
                    return section, None
        else:
            # The name is ["a", "b.c"]
            if section_name_parts[0] in _ref_section._sections:
                # The section already exists in the file
                sub_section = _ref_section._sections[section_name_parts[0]]
                if not isinstance(sub_section, SrcfgSection):
                    return None, f"Cannot use section path through arrays {section_name_parts[0]}"
                return self._add_section(section_name_parts[1], None, sub_section, is_array)
            else:
                # The section does not exist: creates it
                sub_section = SrcfgSection(section_name_parts[0], _ref_section)
                _ref_section._sections[sub_section.name] = sub_section
                return self._add_section(section_name_parts[1], None, sub_section, is_array)

@dataclass
class SrcfgSection:
    name: str
    _parent: Union["SrcfgSection", SrcfgFile]
    _sections: Dict[str, Union["SrcfgSection", List["SrcfgSection"]]] = field(default_factory=lambda: {})
    _entries: Dict[str, str] = field(default_factory=lambda: {})

    def __iter__(self):
        yield from self._entries.items()

    def __contains__(self, name: str):
        return name in self._sections or name in self._entries
    
    def __getitem__(self, name: str):
        if name in self._sections:
            return self._sections[name]
        return self._entries[name]

    def has_section(self, section_name: str):
        return section_name in self._sections
    
    def get_section(self, section_name: str) -> "SrcfgSection":
        section = self._sections[section_name]
        if not isinstance(section, SrcfgSection):
            raise ValueError("Unexpected section list")
        return section
    
    def get_section_list(self, section_name: str) -> Sequence["SrcfgSection"]:
        section = self._sections[section_name]
        if isinstance(section, SrcfgSection):
            raise ValueError("Unexpected section (expected a list)")
        return section
    
    ####

    def has_key(self, name: str):
        return name in self._entries
    
    def get_value(self, key: str, cb: Callable[[str], T]) -> Optional[T]:
        if key not in self._entries:
            return None
        v = self._entries[key]
        return cb(v)
    
    def get_str(self, key: str):
        return self.get_value(key, str)
    
    def get_int(self, key: str):
        return self.get_value(key, int)
    
    def get_float(self, key: str):
        return self.get_value(key, float)
    
    def get_json(self, key: str, relaxed: bool = True):
        def handler(v: str):
            if relaxed:
                matches = re.finditer(r'([0-9a-zA-Z_-]+\s*):', v)
                for match in matches:
                    unquoted_key_with_trail = match.group(1)
                    v = v.replace(
                        unquoted_key_with_trail + ":",
                        '"' + unquoted_key_with_trail.strip() + '":'
                    )
            return json.loads(v)

        return self.get_value(key, handler)


    #####

    ####
    
    def _get_top_section(self) -> "SrcfgSection":
        if isinstance(self._parent, SrcfgFile):
            return self
        else:
            return self._parent._get_top_section()


@dataclass
class SrcfgParseError:
    line_nb: int
    line: str
    message: str = "unable to parse"
    internal_errors: List["SrcfgParseError"] = field(default_factory=lambda: [])

def parse_file(path: Union[str, Path], cwd: Optional[Path] = None):
    if isinstance(path, str):
        if _is_file_path(path):
            path = Path(path) 
        else:
            _path = _find_file(cwd or Path.cwd(), path)
            if _path is None:
                return None, [SrcfgParseError(0, "", "Unable to find file " + path)]
            path = _path

    with path.open("r", encoding="utf-8") as f:
        return parse(f.read(), path.parent)
    
def _find_file(path: Path, name: str):
    if (path / name).exists():
        return path / name
    
    if path.parent == path:
        return None
    
    return _find_file(path.parent, name)

def parse(contents: str, cwd: Optional[Path]) -> Tuple[SrcfgFile, List[SrcfgParseError]]:
    parse_errors: List[SrcfgParseError] = []
    if cwd is None:
        cwd = Path.cwd()

    res = SrcfgFile()

    current_section: Optional[SrcfgSection] = None
    current_key: Optional[str] = None

    line_nb = 0    
    for l in contents.split("\n"):
        line_nb += 1

        stripped_line = l.strip()
        if not stripped_line:
            # ignore empty lines
            continue

        if stripped_line.startswith(COMMENT_PREFIX):
            continue
        if stripped_line.startswith("@import"):
            # Import can be anywhere, appends config files
            # (though it is advised to put at begining of file)
            current_key = None

            file_name_or_path = stripped_line[7:].strip()
            imported_srcfg, errors = parse_file(file_name_or_path, cwd)
            if errors:
                parse_errors.append(SrcfgParseError(line_nb, l, "Got errors when importing file", errors))
            
            if imported_srcfg:
                err = _extend_section(res, imported_srcfg)
                if err:
                    parse_errors.append(SrcfgParseError(line_nb, l, err))
        elif stripped_line.startswith("@insert"):
            # Import can be only within a section
            current_key = None
            if not current_section:
                parse_errors.append(SrcfgParseError(line_nb, l, "Can only use @insert directive inside a section."))
                continue
            raise NotImplementedError()
        elif stripped_line.startswith("["):
            current_key = None
            section_name, is_array = _parse_section_row(stripped_line)
            if not section_name:
                parse_errors.append(SrcfgParseError(line_nb, l))
                continue
            next_current_section, err = res._add_section(section_name, current_section, None, is_array)
            if err or not next_current_section:
                parse_errors.append(SrcfgParseError(line_nb, l, err or f"Unable to add section {section_name}"))
            if next_current_section:
                current_section = next_current_section
        else:
            # A key/value or value only
            if not current_section:
                parse_errors.append(SrcfgParseError(line_nb, l, "Cannot have key/value outside a section"))
                continue

            matches = re.findall(r'^\s*([a-zA-Z0-9_-]*)\s*(:?=)(.*)$', l)
            if not matches:
                # cannot parse line
                parse_errors.append(SrcfgParseError(line_nb, l))
                continue

            if len(matches[0]) != 3:
                parse_errors.append(SrcfgParseError(line_nb, l, f"Unable to parse key/value row."))
                continue
            
            k, op, v = matches[0]

            if not isinstance(k, str) or not isinstance(op, str) or not isinstance(v, str):
                parse_errors.append(SrcfgParseError(line_nb, l, f"Error when separating parts of key/value row."))
                continue

            if op == "=":
                v, parse_value_error = _parse_value(v.strip())
                if parse_value_error or v is None:
                    parse_errors.append(SrcfgParseError(line_nb, l, parse_value_error or "Unable to parse value."))
                    continue
            
            if k:
                # k is null if we continue the previous line
                current_key = k

            if current_key:
                if not k and current_key in current_section._entries:
                    current_section._entries[current_key] += "\n" + v
                else:
                    current_section._entries[current_key] = v
            else:
                parse_errors.append(SrcfgParseError(line_nb, l, "Please specify a key"))

    return res, parse_errors

def _parse_value(v: str) -> Tuple[Optional[str], Optional[str]]:
    # Find all the "${}" and replace by the value the env var

    if COMMENT_PREFIX in v:
        v = v[:v.index(COMMENT_PREFIX)].strip()

    matches = re.finditer(r'\${(.+)}', v)
    for match in matches:
        var_name = match.group(1)
        if var_name in os.environ:
            replacement = os.environ[var_name]
            v = v.replace(match.group(0), replacement)
        else:
            return None, "Unable to find env var " + var_name
        
    return v, None

def _extend_section(dst: Union[SrcfgSection, SrcfgFile], src: Union[SrcfgSection, SrcfgFile]) -> Optional[str]:
    """
    Adds or overrides entries in src to dst
    Adds ot extends sections in src to dst
    Note: sections from src are not copied: beware of side effects !!
    """
    if isinstance(dst, SrcfgSection):
        if not isinstance(src, SrcfgSection):
            return f"Cannot add key values outside a section"
        for key, value in src:
            dst._entries[key] = value
    for name, src_section in src._sections.items():
        if name in dst._sections:
            dst_section = dst._sections[name]
            if isinstance(dst_section, SrcfgSection):
                # The destination is not an array
                if isinstance(src_section, SrcfgSection):
                    err = _extend_section(dst_section, src_section)
                    if err:
                        return err
                else:
                    return f"Unable to merge section {name}: cannot merge section with list"
            else:
                # The destination is an array
                if isinstance(src_section, SrcfgSection):
                    return f"Unable to merge section {name}: cannot merge section with list"
                else:
                    dst_section.extend(src_section)
        else:
            dst._sections[name] = src_section

def _parse_section_row(l: str):
    m = re.findall("^\\[([\\sa-zA-Z0-9_\\.-]+)\\]$", l)
    if m:
        # A regular section (not array)
        return m[0].strip(), False
    m = re.findall("^\\[\\[([a-zA-Z0-9_\\.-]+)\\]\\]$", l)
    if m:
        # An array section
        return m[0].strip(), True
    
    return None, False

def _is_file_path(path_or_name: str) -> bool:
    # Normalize the path to handle different path separators on Windows and Unix-like systems.
    normalized_path = os.path.normpath(path_or_name)
    
    # Check if the string contains any path separators.
    if os.path.sep in normalized_path or normalized_path.startswith("~"):
        return True

    # Check if the string starts with "./" to indicate a relative file path.
    if normalized_path.startswith("." + os.path.sep):
        return True
    
    return False