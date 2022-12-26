"""Formatting utils and functions."""
import textwrap

from .utils import variables_dict
from .variable import VarIntent, VarType


def _calculate_col_width(col_items):
    max_name_length = max((len(s) for s in col_items)) if col_items else 0
    col_width = max(max_name_length, 7) + 6
    return col_width


def pretty_print(s, numchars):
    """Format the returned string so that it is numchars long,
    padding with trailing spaces or truncating with ellipses as
    necessary.
    """
    s = maybe_truncate(s, numchars)
    return s + " " * max(numchars - len(s), 0)


def maybe_truncate(s, maxlen=500):
    if len(s) > maxlen:
        s = s[: (maxlen - 3)] + "..."
    return s


def wrap_indent(text, start="", length=None):
    if length is None:
        length = len(start)
    indent = "\n" + " " * length
    return start + indent.join(x for x in text.splitlines())


def _summarize_var(var, process, col_width):
    max_line_length = 70

    var_name = var.name
    var_type = var.metadata["var_type"]
    var_intent = var.metadata["intent"]

    if var_intent == VarIntent.IN:
        link_symbol = "<---"
        var_intent_str = "   [in]"
    elif var_intent == VarIntent.OUT:
        link_symbol = "--->"
        var_intent_str = "  [out]"
    else:
        var_intent_str = "[inout]"

    if var_type == VarType.GROUP:
        var_info = f"{link_symbol} group {var.metadata['group']!r}"

    elif var_type == VarType.FOREIGN:
        key = process.__xsimlab_state_keys__.get(var_name)
        if key is None:
            key = process.__xsimlab_od_keys__.get(var_name)
        if key is None:
            key = (
                var.metadata["other_process_cls"].__name__,
                var.metadata["var_name"],
            )

        var_info = f"{link_symbol} {'.'.join(key)}"

    else:
        var_dims = " or ".join([str(d) for d in var.metadata["dims"]])

        if var_dims != "()":
            var_info = " ".join([var_dims, var.metadata["description"]])
        else:
            var_info = var.metadata["description"]

    left_col = pretty_print(f"    {var.name}", col_width)

    right_col = var_intent_str
    if var_info:
        right_col += maybe_truncate(" " + var_info, max_line_length - col_width - 7)

    return left_col + right_col


def var_details(var, max_line_length=70):
    var_metadata = var.metadata.copy()

    description = textwrap.fill(
        var_metadata.pop("description").capitalize(), width=max_line_length
    )
    if not description:
        description = "(no description given)"

    detail_items = [
        ("type", var_metadata.pop("var_type").value),
        ("intent", var_metadata.pop("intent").value),
    ]
    detail_items += list(var_metadata.items())

    details = "\n".join([f"- {k} : {v}" for k, v in detail_items])

    return description + "\n\n" + details + "\n"


def add_attribute_section(process, placeholder="{{attributes}}"):
    data_type = "object"  # placeholder until issue #34 is solved

    fmt_vars = []

    for vname, var in variables_dict(process).items():
        var_header = f"{vname} : {data_type}"
        var_content = textwrap.indent(var_details(var, max_line_length=62), " " * 4)

        fmt_vars.append(f"{var_header}\n{var_content}")

    fmt_section = textwrap.indent(
        "Attributes\n" "----------\n" + "\n".join(fmt_vars), " " * 4
    )

    current_doc = process.__doc__ or ""

    if placeholder in current_doc:
        new_doc = current_doc.replace(placeholder, fmt_section[4:])
    else:
        new_doc = f"{current_doc}\n{fmt_section}\n"

    return new_doc


def repr_process(process):
    process_cls = type(process)

    if process.__xsimlab_name__ is not None:
        process_name = f"{process.__xsimlab_name__!r}"
    else:
        process_name = ""

    header = f"<{process_cls.__name__} {process_name} (xsimlab process)>"

    variables = variables_dict(process_cls)

    col_width = _calculate_col_width(variables)

    var_section_summary = "Variables:"
    var_section_details = "\n".join(
        [_summarize_var(var, process, col_width) for var in variables.values()]
    )
    if not var_section_details:
        var_section_details = "    *empty*"

    stages_implemented = [
        "    {}".format(s) for s in process.__xsimlab_executor__.stages
    ]

    stages_section_summary = "Simulation stages:"
    if stages_implemented:
        stages_section_details = "\n".join(stages_implemented)
    else:
        stages_section_details = "    *no stage implemented*"

    process_repr = "\n".join(
        [
            header,
            var_section_summary,
            var_section_details,
            stages_section_summary,
            stages_section_details,
        ]
    )

    return process_repr + "\n"


def repr_model(model):
    n_processes = len(model)

    header = (
        f"<xsimlab.Model ({n_processes} processes, {len(model.input_vars)} inputs)>"
    )

    if not n_processes:
        return header + "\n"

    col_width = _calculate_col_width([var_name for _, var_name in model.input_vars])

    sections = []

    for p_name, p_obj in model.items():
        p_section = p_name

        p_input_vars = model.input_vars_dict.get(p_name, [])
        input_var_lines = []

        for var_name in p_input_vars:
            var = variables_dict(type(p_obj))[var_name]
            input_var_lines.append(_summarize_var(var, p_obj, col_width))

        if input_var_lines:
            p_section += "\n" + "\n".join(input_var_lines)

        sections.append(p_section)

    return header + "\n" + "\n".join(sections) + "\n"
