#!/usr/bin/env python
# -*-coding:utf-8-*-

import pandas as pd
from pandas import Series, DataFrame
import numpy as np
from scipy.stats import mode
import csv
import matplotlib.dates
import matplotlib.pyplot as plt
from datetime import *
import urllib, urllib.parse, urllib.request
import json, random
from sklearn.preprocessing import *
from sklearn.model_selection import train_test_split, KFold, GridSearchCV, StratifiedKFold


# 导入数据
def importDf(url, sep='\t', na_values=None, header=None, index_col=None, colNames=None):
    df = pd.read_table(url, names=colNames, header=header, encoding='utf-8', quoting=3)
    return df

# 添加one-hot编码并保留原字段
def addOneHot(df, colName):
    if isinstance(colName, str):
        colName = [colName]
    colTemp = df[colName]
    df = pd.get_dummies(df, columns=colName)
    df = pd.concat([df, colTemp], axis=1)
    return df

def labelEncoding(df, colList):
    '''
    将标称值转成编码
    '''
    for col in colList:
        df.loc[df[col].notnull(),col] = LabelEncoder().fit_transform(df.loc[df[col].notnull(),col])
        df[col] = df[col].astype(float)
    return df

# 缩放字段至0-1
def scalerFea(df, cols):
    df.dropna(inplace=True, subset=cols)
    scaler = MinMaxScaler()
    df[cols] = scaler.fit_transform(df[cols].values)
    return df,scaler

# 对数组集合进行合并操作
def listAdd(l):
    result = []
    [result.extend(x) for x in l]
    return result

# 对不同标签进行抽样处理
def getSubsample(labelList, ratio=0.8, repeat=False, params=None):
    if not isinstance(params, dict):
        if isinstance(ratio, (float, int)):
            params = {k:{'ratio':ratio, 'repeat':repeat} for k in set(labelList)}
        else:
            params={k:{'ratio':ratio[k], 'repeat':repeat} for k in ratio.keys()}
    resultIdx = []
    for label in params.keys():
        param = params[label]
        tempList = np.where(labelList==label)[0]
        sampleSize = np.ceil(len(tempList)*params[label]['ratio']).astype(int)
        if (~param['repeat'])&(param['ratio']<=1):
            resultIdx.extend(random.sample(tempList.tolist(),sampleSize))
        else:
            resultIdx.extend(tempList[np.random.randint(len(tempList),size=sampleSize)])
    return resultIdx

# 矩估计法计算贝叶斯平滑参数
def countBetaParamByMME(inputArr, epsilon=0):
    EX = inputArr.mean()
    DX = inputArr.var() + epsilon / len(inputArr)  # 加上极小值防止除以0
    alpha = (EX*(1-EX)/DX - 1) * EX
    beta = (EX*(1-EX)/DX - 1) * (1-EX)
    return alpha,beta

# 对numpy数组进行贝叶斯平滑处理
def biasSmooth(aArr, bArr, method='MME', epsilon=0, alpha=None, beta=None):
    ratioArr = aArr / bArr
    if method=='MME':
        if len(ratioArr[ratioArr==ratioArr]) > 1:
            alpha,beta = countBetaParamByMME(ratioArr[ratioArr==ratioArr], epsilon=epsilon)
        else:
            alpha = beta = 0
        # print(alpha+beta, alpha / (alpha+beta))
    resultArr = (aArr+alpha) / (bArr+alpha+beta)
    return resultArr

def getPredLabel(predArr, threshold=None, tops=None):
    '''
    根据阈值返回分类预测结果
    '''
    if tops is not None :
        temp = np.sort(np.array(predArr))
        if tops < 1:
            threshold = temp[-1*round(len(temp)*tops)]
        else:
            threshold = temp[-round(tops)]
    if threshold is None:
        print('[Error] could not get threshold value.')
        exit()
    return (predArr>=threshold).astype(int)

def findF1Threshold(predictList, labelList):
    '''
    寻找F1最佳阈值
    '''
    tempDf = pd.DataFrame({'predict':predictList, 'label':labelList})
    trueNum = len(tempDf[tempDf.label==1])
    thrList = np.unique(tempDf['predict'])
    f1List = []
    for thr in thrList:
        tempDf['temp'] = getPredLabel(tempDf['predict'], thr)
        TP = len(tempDf[(tempDf.label==1)&(tempDf.temp==1)])
        if TP==0:
            break
        positiveNum = len(tempDf[tempDf.temp==1])
        precise = TP / positiveNum
        recall = TP / trueNum
        f1 = 2 * precise * recall / (precise + recall)
        f1List.append(f1)
    f1Df = pd.DataFrame({'thr':thrList[:len(f1List)], 'f1':f1List}).sort_values(by=['f1','thr'], ascending=[False,True])
    bestThs = thrList[f1List.index(max(f1List))]
    averThr = f1Df.head(5).sort_values(by=['thr']).head(4)['thr'].mean()    # 取前5，去掉最大阈值后取平均
    # print('tops 5 thr:\n', f1Df.head(5),'aver thr:',averThr)
    return averThr

# 导出预测结果
def exportResult(df, filePath, header=True, index=False, sep=','):
    df.to_csv(filePath, sep=sep, header=header, index=index)

# 获取stacking下一层数据集
def getOof(clf, trainX, trainY, testX, nFold=5, stratify=True, verbose=False, random_state=0, weight=None):
    startTime = datetime.now()
    oofTrain = np.zeros(trainX.shape[0])
    oofTest = np.zeros(testX.shape[0])
    oofTestSkf = np.zeros((testX.shape[0], nFold))
    if stratify:
        kf = StratifiedKFold(n_splits=nFold, random_state=random_state, shuffle=True)
    else:
        kf = KFold(n_splits=nFold, random_state=random_state, shuffle=True)
    for i, (trainIdx, testIdx) in enumerate(kf.split(trainX, trainY)):
        kfTrainX = trainX[trainIdx]
        kfTrainY = trainY[trainIdx]
        kfTestX = trainX[testIdx]
        kfTesty = trainY[testIdx]
        # if weight is not None:
        #     kfWeight = weight[trainIdx]
        # else:
        #     kfWeight = None
        clf.train(kfTrainX, kfTrainY, validX=kfTestX, validy=kfTesty, verbose=verbose)
        oofTrain[testIdx] = clf.predict(kfTestX)
        oofTestSkf[:,i] = clf.predict(testX)
        print('oof cv %d of %d: finished!' % (i+1, nFold))
    oofTest[:] = oofTestSkf.mean(axis=1)
    print('oof cost time:', datetime.now() - startTime)
    return oofTrain, oofTest

if __name__ == '__main__':
    findF1Threshold([0.1,0.15,0.2,0.25,0.3,0.35,0.4,0.45,0.5,0.55,0.6,0.65],[0,0,0,0,0,0,1,1,1,1,0,0])
    # findF1Threshold([0.3,0.6,0.3,0.5,0.2,0.7,0.8],[0,1,0,0,1,1,0])
    getPredLabel(pd.Series([0.3,0.6,0.3,0.5,0.2,0.7,0.8]), tops=0.3)
