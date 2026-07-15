import numpy as np 
from random import gauss 
from itertools import product 

def main():
    rPT=rSLM=np.linspace(0,10,21)
    count = 0 
    for prod_ in product([10,5,0,-5,-10],[5,10,25,50,100]):
        count+=1
        coeffs={'forecast':prod_[0],'hl':prod_[1],'sigma':1}
        output=batch(coeffs,nIter=100000,maxHP=100,rPT=rPT,rSLm=rSLM)
    return output

