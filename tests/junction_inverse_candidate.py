"""Unadopted candidate; full-stroke regression despite faster matrix solve."""
def _junction_length_inverse(rows):
    """Solve the two handle lengths; callers append the 0.1 identity prior.

    Unit direction vectors and fixed Bernstein samples bound the Gram matrix.
    The positive diagonal prior also keeps parallel/opposite directions regular.
    This helper is intentionally not a general replacement for pseudoinverse.
    """
    import numpy as np
    trans = rows.transpose(0, 2, 1)
    gram = trans @ rows
    a = gram[:, 0, 0]; b = gram[:, 0, 1]; c = gram[:, 1, 1]
    determinant = a*c-b*b
    result = np.empty_like(trans)
    result[:, 0] = (c[:, None]*trans[:, 0]-b[:, None]*trans[:, 1])/determinant[:, None]
    result[:, 1] = (a[:, None]*trans[:, 1]-b[:, None]*trans[:, 0])/determinant[:, None]
    return result


