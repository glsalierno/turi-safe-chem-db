"""
Stub module for assess() spine capability.

Superseded by auto_p2oasys (PR F, #12). Maintained only for backward compatibility.
See packages.auto_p2oasys for the current implementation.
"""


def assess(cas: str, **kwargs) -> dict:
    """
    Stub assess function - superseded by auto_p2oasys.
    
    Raises NotImplementedError directing users to auto_p2oasys.
    """
    raise NotImplementedError(
        "assess() is superseded by auto_p2oasys(). "
        "Use: from packages.auto_p2oasys import auto_p2oasys"
    )
