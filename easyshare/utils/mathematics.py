def rangify(v, lb, ub):
    """ Returns a value bounded to a lower and an upper bound """
    if lb >= ub:
        lb, ub = ub, lb
    return max(min(v, ub), lb)
