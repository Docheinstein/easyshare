def rangify(v, lb, ub):
    if lb >= ub:
        lb, ub = ub, lb
    return max(min(v, ub), lb)
