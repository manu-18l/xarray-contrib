# coding: utf-8
import itertools


class AbstractVariable(object):
    """Abstract class for all variables.

    This class aims at providing a common parent class
    for all regular, diagnostic, foreign and undefined variables.

    """
    def __init__(self, provided=False, description='', attrs=None):
        self.provided = provided
        self.description = description
        self.attrs = attrs


class Variable(AbstractVariable):
    """Base class that represents a variable in a process or a model.

    `Variable` objects store useful metadata such as dimension labels,
    a short description, a default value or other user-provided metadata.

    Variables allow to convert any given value to a `xarray.Variable` object
    after having perfomed some sanity checks.

    In processes, variables are instantiated as class attributes. They
    represent fundamental elements of a process interface (see
    :class:`Process`) and by extension a model interface.
    Some attributes such as `provided` and `optional` also contribute to
    the definition of the interface.

    """
    default_validators = []  # Default set of validators

    def __init__(self, dims, kind='state_only', provided=False,
                 optional=False, default_value=None, validators=(),
                 description='', attrs=None):
        """
        Parameters
        ----------
        dims : str or tuple or list
            Dimension label(s) of the variable. An empty tuple corresponds
            to a scalar variable, a string or a 1-length tuple corresponds
            to a 1-d variable and a n-length tuple corresponds to a n-d
            variable. A list of str or tuple items may also be provided if
            the variable accepts different numbers of dimensions.
        kind : {'state_only', 'state_rate'}, optional
            A 'state_rate' variable accepts two values: a state and a rate
            (i.e., a time-derivative), while a 'state_only' variable (default)
            has only a state value.
        provided : bool, optional
            Defines whether a value for the variable is required (False)
            or provided (True) by the process in which it is defined
            (default: False).
            If `provided=True`, then the variable in a process/model won't
            be considered as an input of that process/model.
        optional : bool, optional
            True if a value is required for the variable (default: False).
            Ignored when `provided` is True.
        default_value : any, optional
            Single default value for the variable (default: None). It
            will be automatically broadcasted to all of its dimensions.
            Ignored when `provided` is True.
        validators : tuple or list, optional
            A list of callables that take an `xarray.Variable` object and
            raises a `ValidationError` if it doesn’t meet some criteria.
            It may be useful for custom, advanced validation that
            can be reused for different variables.
        description : str, optional
            Short description of the variable (one-line).
        attrs : dict, optional
            Dictionnary of additional metadata (e.g., standard_name,
            units, math_symbol...).

        """
        super(Variable, self).__init__(
            provided=provided, description=description, attrs=attrs
        )

        self.dims = dims
        self.optional = optional
        self.kind = kind
        self.default_value = default_value
        self._validators = list(validators)
        self._state = None

    @property
    def validators(self):
        return list(itertools.chain(self.default_validators, self._validators))

    def run_validators(self, variable):
        for vfunc in self.validators:
            vfunc(variable)

    def validate(self, xr_variable):
        pass

    @property
    def state(self):
        return self._state

    @state.setter
    def state(self, value):
        self._state = value


class ForeignVariable(AbstractVariable):
    """Reference to a variable that is defined in another `Process` class.

    """
    def __init__(self, other_process, var_name, provided=False):
        """
        Parameters
        ----------
        other_process : str or class
            Class or class name in which the variable is defined.
        var_name : str
            Name of the corresponding class attribute in `other_process`.
            The value of this class attribute must be a `Variable` object.
        provided : bool, optional
            Defines whether a value for the variable is required (False) or
            provided (True) by the process in which this reference is
            defined (default: False).

        """
        super(ForeignVariable, self).__init__(provided=provided)

        self.other_process = other_process
        self._other_process_obj = None
        self.var_name = var_name

    def assign_other_process_obj(self, other_process_obj):
        self._other_process_obj = other_process_obj

    @property
    def ref_var(self):
        """The original variable object."""

        if self._other_process_obj is None:
            cls_or_obj = self.other_process
        else:
            cls_or_obj = self._other_process_obj

        return cls_or_obj._variables[self.var_name]

    @property
    def state(self):
        return self.ref_var._state

    @state.setter
    def state(self, value):
        self.ref_var.state = value


class DiagnosticVariable(AbstractVariable):
    """Variable for model diagnostic purpose only.

    The value of a diagnostic variable is computed on the fly during a
    model run (there is no initialization nor update of any state).

    A diagnostic variable is defined inside a `Process` subclass, but
    it shouldn't be created directly as a class attribute.
    Instead it should be defined by applying the `@diagnostic` decorator
    on a method of that class.

    Diagnostic variables declared in a process should never be referenced
    in other processes as foreign variable.

    The diagnostic variables declared in a process are computed after the
    execution of all processes in a model at the end of a time step.

    """
    def __init__(self, func, description='', attrs=None):
        super(DiagnosticVariable, self).__init__(
            provided=True, description=description, attrs=attrs
        )

        self._func = func
        self._process_obj = None

    def assign_process_obj(self, process_obj):
        self._process_obj = process_obj

    @property
    def state(self):
        return self._func(self._process_obj)

    def __call__(self):
        return self._func(self._process_obj)


class UndefinedVariable(AbstractVariable):
    """Represent variable(s) that has to be defined later, i.e.,
    when creating a new `Process` object.

    Undefined variables are useful in cases when we want to reuse
    the same process in different contexts without having to re-write
    other `Process` subclasses. Good examples are processes that
    aggregate (e.g., sum, product, mean) variables provided by
    other processes.

    """
    def __init__(self):
        super(UndefinedVariable, self).__init__(provided=False)


def diagnostic(attrs_or_function=None, attrs=None):
    """Applied to a method of a `Process` subclass, this decorator
    allows registering that method as a diagnostic variable.

    The method's docstring is used as a description of the
    variable (it should be short, one-line).

    Parameters
    ----------
    attrs : dict (optional)
        Variable metadata (e.g., standard_name, units, math_symbol...).

    Examples
    --------
    @diagnostic
    def slope(self):
        '''topographic slope'''
        return self._compute_slope()

    @diagnostic({'units': '1/m'})
    def curvature(self):
        '''terrain curvature'''
        return self._compute_curvature()

    """
    func = None
    if callable(attrs_or_function):
        func = attrs_or_function
    elif isinstance(attrs_or_function, dict):
        attrs = attrs_or_function

    def _add_diagnostic_attrs(function):
        function._diagnostic = True
        function._diagnostic_attrs = attrs
        return function

    if func is not None:
        return _add_diagnostic_attrs(func)
    else:
        return _add_diagnostic_attrs
