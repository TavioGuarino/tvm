# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
# pylint: disable=no-else-return
# pylint: disable=unidiomatic-typecheck
"""
This file contains the pass manager for Relay which exposes different
granularity of interfaces for users to implement and use passes more
conveniently.
"""
import types

from tvm._ffi.runtime_ctypes import TVMContext
from . import _transform
from .base import RelayNode, register_relay_node
from .. import nd as _nd


@register_relay_node
class PassInfo(RelayNode):
    """The class that contains the meta data required by a pass. It is the
    container of information needed by running an optimization or analysis.
    This class can be extended by adding new members when more meta data is
    needed.

    Parameters
    ----------
    name : str
        The pass name.

    opt_level : int
        The optimization level of this pass.

    required : List[str]
        The list of passes that are required by a certain pass.
    """

    def __init__(self, name, opt_level, required=None):
        self.__init_handle_by_constructor__(_transform.PassInfo, name, opt_level,
                                            required)


@register_relay_node
class PassContext(RelayNode):
    """The basis where a Relay optimization/analysis runs on.
    Each pass context contains a number of auxiliary information that is used
    to help an optimization pass. Such information includes the error reporter
    to record the errors of during the optimization, etc.

    opt_level : Optional[int]
        The optimization level of this pass.

    fallback_device : Optional[Union[int, str, TVMContext]]
        The fallback device type. It is also used as the default device for
        operators that are not annotated during heterogeneous execution.

    required_pass : Optional[Union[List[str], Set[str], Tuple[str]]]
        The list of passes that are required by a certain pass.

    disabled_pass : Optional[Union[List[str], Set[str], Tuple[str]]]
        The list of passes that are disabled.
    """
    def __init__(self,
                 opt_level=2,
                 fallback_device=_nd.cpu(),
                 required_pass=None,
                 disabled_pass=None):
        if isinstance(fallback_device, str):
            fallback_device = _nd.context(fallback_device).device_type
        elif isinstance(fallback_device, TVMContext):
            fallback_device = fallback_device.device_type
        if not isinstance(fallback_device, int):
            raise TypeError("required_pass is expected to be the type of " +
                            "int/str/TVMContext.")

        required = list(required_pass) if required_pass else []
        if not isinstance(required, (list, tuple)):
            raise TypeError("required_pass is expected to be the type of " +
                            "list/tuple/set.")

        disabled = list(disabled_pass) if disabled_pass else []
        if not isinstance(disabled, (list, tuple)):
            raise TypeError("disabled_pass is expected to be the type of " +
                            "list/tuple/set.")

        self.__init_handle_by_constructor__(_transform.PassContext, opt_level,
                                            fallback_device, required,
                                            disabled)

    def __enter__(self):
        _transform.EnterPassContext(self)
        return self

    def __exit__(self, ptype, value, trace):
        _transform.ExitPassContext(self)

    @staticmethod
    def current():
        """Return the current pass context."""
        return _transform.GetCurrentPassContext()


def build_config(opt_level=2,
                 fallback_device=_nd.cpu(),
                 required_pass=None,
                 disabled_pass=None):
    """Configure the build behavior by setting config variables.

    Parameters
    ----------
    opt_level: int, optional
        Optimization level. The optimization pass name and level are as the
        following:

        .. code-block:: python

            OPT_PASS_LEVEL = {
                "SimplifyInference": 0,
                "OpFusion": 1,
                "FoldConstant": 2,
                "CombineParallelConv2D": 3,
                "FoldScaleAxis": 3,
                "AlterOpLayout": 3,
                "CanonicalizeOps": 3,
                "EliminateCommonSubexpr": 3,
            }

    fallback_device : int, str, or tvm.TVMContext, optional
        The fallback device. It is also used as the default device for
        operators without specified device during heterogeneous execution.

    required_pass: set of str, optional
        Optimization passes that are required regardless of optimization level.

    disabled_pass: set of str, optional
        Optimization passes to be disabled during optimization.

    Returns
    -------
    pass_context: PassContext
        The pass context for optimizations.
    """
    return PassContext(opt_level, fallback_device, required_pass,
                       disabled_pass)


@register_relay_node
class Pass(RelayNode):
    """The base class of all passes. All methods here are just simple wrappers
    that are implemented in the backend. They are defined for users to
    conveniently interact with the base class.
    """

    @property
    def info(self):
        """Get the pass meta."""
        return _transform.Info(self)

    def __call__(self, mod):
        """Execute the pass. Note that for sequential pass, the dependency among
        different passes will be resolved in the backend.

        Parameters
        ----------
        mod : tvm.relay.Module
            The module that a certain optimization is performed on.

        Returns
        -------
        mod : tvm.relay.Module
            The updated module after applying this pass.
        """
        return _transform.RunPass(self, mod)


@register_relay_node
class ModulePass(Pass):
    """A pass that works on tvm.relay.Module. Users don't need to interact with
    this class directly. Instead, a module pass should be created through
    `module_pass`, because the design of the `module_pass` API is flexible
    enough to handle the creation of a module pass in different manners. In
    addition, all members of a module pass can be accessed from the base class.
    The same rule applies to FunctionPass and Sequential as well.
    """


@register_relay_node
class FunctionPass(Pass):
    """A pass that works on each tvm.relay.Function in a module. A function
    pass class should be created through `function_pass`.
    """


@register_relay_node
class Sequential(Pass):
    """A pass that works on a sequence of pass objects. Multiple passes can be
    executed sequentially using this class.

    Some typical usage of the sequential pass are:
    1. Users provide a list of passes for optimization.
    2. Only an optimization level is provided so that the backend system has
       to glob all passes at this level and below to perform the optimizations.
    Note that users can also provide a series of passes that they don't want to
    apply when running a sequential pass. Pass dependency will be resolved in
    the backend as well.

    Parameters
    ----------
    passes : Optional[List[Pass]]
        A sequence of passes candidate for optimization.

    opt_level : Optional[int]
        The optimization level of this sequential pass.

    name : Optional[str]
        The name of the sequential pass.

    required : Optional[List[str]]
        The list of passes that the sequential pass is dependent on.
    """

    def __init__(self,
                 passes=None,
                 opt_level=2,
                 name="sequential",
                 required=None):
        passes = passes if passes else []
        if not isinstance(passes, (list, tuple)):
            raise TypeError("passes must be a list of Pass objects.")

        required = required if required else []
        if not isinstance(required, (list, tuple)):
            raise TypeError("Required is expected to be the type of list/tuple.")

        self.__init_handle_by_constructor__(_transform.Sequential,
                                            passes, opt_level, name, required)


def module_pass(pass_func=None, opt_level=None, name=None, required=None):
    """Create a module pass. This function returns a callback when pass_func
    is provided. Otherwise, it returns the created module level pass using the
    given optimization function.

    Parameters
    ----------
    pass_func : Optional[Callable[(Module/Function, PassContext) ->
                Module/Function]]
        The implemented optimization pass.

    opt_level : int
        The optimization level of this module pass.

    name : Optional[str]
        The name of the module pass. The name could be empty. In this case, the
        name of the optimization function will be used as the pass name.

    required : Optional[List[str]]
        The list of passes that the module pass is dependent on.

    Returns
    -------
    create_module_pass : Union[Callable, ModulePass]
        The callable that will create a module pass is returned when
        pass_func is not passed in. Otherwise, a ModulePass object will be
        directly created.

	Examples
    --------
    The following code creates a module level pass and adds an abs function to
    the module.

    .. code-block:: python

        @relay.transform.module_pass(opt_level=2)
        def transform(mod, ctx):
            tp = relay.TensorType((10,), "float32")
            x = relay.var("x", tp)
            gv = relay.GlobalVar("var")
            func = relay.Function([x], relay.abs(x))
            new_mod = relay.Module({gv: func})
            new_mod.update(mod)
            return new_mod

        module_pass = transform
        assert isinstance(module_pass, transform.ModulePass)
        assert module_pass.info.opt_level == 2

        # Given a module m, the optimization could be invoked as the follwoing:
        updated_mod = module_pass(m)
        # Now a function abs should be added to the module m.
    """

    if opt_level is None:
        raise ValueError("Please provide opt_level for the module pass.")

    required = required if required else []
    if not isinstance(required, (list, tuple)):
        raise TypeError("Required is expected to be the type of " +
                        "list/tuple.")

    def create_module_pass(pass_func):
        """Internal function that creates a module pass"""
        if not isinstance(pass_func, (types.FunctionType, types.LambdaType)):
            raise TypeError("pass_func must be a callable for Module pass")

        return _transform.CreateModulePass(
            pass_func, opt_level, name if name else pass_func.__name__,
            required)

    if pass_func:
        return create_module_pass(pass_func)
    return create_module_pass


def function_pass(pass_func=None, opt_level=None, name=None, required=None):
    """Create a function pass. This function returns a callback when pass_func
    is provided. Otherwise, it returns the created function pass using the
    given optimization function.

    Parameters
    ----------
    pass_func : Optional[Callable[(Module/Function, PassContext) ->
                Module/Function]]
        The implemented optimization pass.

    opt_level : int
        The optimization level of this module pass.

    name : Optional[str]
        The name of the function pass. The name could be empty. In this case, the
        name of the optimization function will be used as the pass name.

    required : Optional[List[str]]
        The list of passes that the module pass is dependent on.

    Returns
    -------
    create_function_pass : Union[Callable, FunctionPass]
        The callable that will create a function pass is returned when
        pass_func is not passed in. Otherwise, a FunctionPass object will be
        created.

    Examples
    --------
    The following code creates a function level pass that performs constant
    folding.

    .. code-block:: python

        @relay.transform.function_pass(opt_level=2)
        def transform(func, ctx):
            return ir_pass.fold_constant(func)

        function_pass = transform
        assert isinstance(function_pass, transform.FunctionPass)
        assert function_pass.info.opt_level == 2

        # Given a module m, the optimization could be invoked as the follwoing:
        updated_mod = function_pass(m)
        # Now constant folding should have been applied to every function in
        # the provided module m. And the updated module will be returned.
    """

    if opt_level is None:
        raise ValueError("Please provide opt_level for the funtion pass.")

    required = required if required else []
    if not isinstance(required, (list, tuple)):
        raise TypeError("Required is expected to be the type of " +
                        "list/tuple.")

    def create_function_pass(pass_func):
        """Internal function that creates a function pass"""
        if not isinstance(pass_func, (types.FunctionType, types.LambdaType)):
            raise TypeError("pass_func must be a callable for Module pass")

        return _transform.CreateFunctionPass(
            pass_func, opt_level, name if name else pass_func.__name__,
            required)

    if pass_func:
        return create_function_pass(pass_func)
    return create_function_pass
