# -*- coding: utf-8 -*-

import os
import xmltodict
from OLP.Readers.ReaderTools import UniPrinter
from OLP.Readers.CMSBReaders import CMSBReader
from OLP.Readers.LoanFilter import getFilter
# from OLP.Readers.FeatureBuilder import FeatureBuilder
# from OLP.Readers.ProdContactCounter import ProdContactCounter
# from OLP.Readers.TransCounter import TransCounter
# from OLP.Readers.LabelReader import LabelReader
from OLP.core.samples import Sample, Samples
from OLP.Readers.SamplesBuilder import SamplesBuilder
from OLP.core.models import get_classifier
from OLP.core.metrics import get_metric
import config as cf


def filterLoans(filterNames, fieldName2Index, loans, custNum2ProtolNums):
    '''
    根据指定规则过滤贷款协议数据

    Args:
        filterNames (list): 过滤器名称列表
        fieldName2Index (dict): 贷款协议表字段索引
        loans (dict): 贷款协议表数据

    Returns:
        dict: 过滤后的贷款协议表数据
    '''
    filters = [getFilter(filterName) for filterName in filterNames]
    for filter_ in filters:
        fieldName2Index, loans, custNum2ProtolNums = filter_.filter(fieldName2Index, loans, custNum2ProtolNums)
    return loans


def gen_samples(x_indexes, cust_num_protol_nums, feats, labels):
    '''
    将原有数据记录转为Samples格式
    '''
    samples = Samples(x_indexes)
    for feat, label in zip(feats, labels):
        cust_num = feat[0]
        protol_nums = cust_num_protol_nums[cust_num]
        X = feat[1]
        y = label[1]
        sample = Sample(cust_num, protol_nums, X, y)
        samples.append(sample)
    return samples


def get_x_importances(samples):
    '''
    计算特征重要性

    Args:
        samples (Samples): 训练样本

    Returns:
        dict: 特征重要性，格式为{特征1: 重要性1, 特征2: 重要性2, ...}
    '''
    model_name = 'OLP.core.models.RandomForestClassifier'
    model_param = {'n_estimators': 100}
    clf = get_classifier(model_name, model_param)
    Xs = samples.get_Xs()
    ys = samples.get_ys()
    clf.fit(Xs, ys)

    x_indexes = samples.get_x_indexes()
    x_importances = {}
    x_importances_ = clf.get_x_importances()
    for x, index in x_indexes.iteritems():
        x_importances[x] = x_importances_[index]

    return x_importances


def analyze_samples(trn_samples, tst_samples, n, filename):
    '''
    分析样本中逾期客户的风险点

    Args:
        trn_samples (Samples): 训练样本
        tst_samples (Samples): 测试样本
        n (int): 取top n个重要特征
        filename (str): 结果文件
    '''
    x_importances = get_x_importances(trn_samples)
    top_n_xs = sorted(x_importances.keys(), key=lambda item: x_importances[item])[: n]  # 取top n个重要特征

    x_indexes = trn_samples.get_x_indexes()

    tst_pos_samples = Samples(x_indexes, [sample for sample in tst_samples if sample.get_y_pred() == cf.OVERDUE])  # 逾期客户
    trn_neg_samples = Samples(x_indexes, [sample for sample in trn_samples if sample.get_y() == cf.NON_OVERDUE])  # 正常客户
    trn_neg_avg_X = trn_neg_samples.get_avg_X()
    trn_neg_std_X = trn_neg_samples.get_std_X()

    with open(filename, 'w') as outfile:
        d = {'samples': {'sample': []}}
        for sample in tst_pos_samples:
            s = {}
            s['cust_num'] = sample.get_cust_num()
            s['protol_nums'] = {'protol_num': sample.get_protol_nums()}
            s['y_pred'] = sample.get_y_pred()
            X = sample.get_X()
            ratios = []
            for name in top_n_xs:
                index = x_indexes[name]
                x = X[index]
                avg_x = trn_neg_avg_X[index]
                std_x = trn_neg_std_X[index]
                ratio = abs(x - avg_x) / std_x
                ratios.append([name, x, avg_x, std_x, ratio])
            ratios.sort(key=lambda item: item[4], reverse=True)
            s['X'] = {'x': []}
            for name, x, avg_x, std_x, ratio in ratios:
                s['X']['x'].append({'ratio': str(ratio), 'val': str(x), 'avg_val': str(avg_x), 'std_val': str(std_x), '@name': name.decode('utf-8')})
            d['samples']['sample'].append(s)
        xml = xmltodict.unparse(d, pretty=True).encode('utf-8')
        outfile.write(xml)


def fit_predict(model_name, model_param, trn_samples, tst_samples):
    '''
    利用训练样本训练模型并对测试样本进行预测

    Args:
        model_name (str): 模型名称
        model_param (dict): 模型参数
        trn_samples (Samples): 训练样本
        tst_samples (Samples): 测试样本
    '''
    trn_Xs = trn_samples.get_Xs()
    trn_ys = trn_samples.get_ys()
    tst_Xs = tst_samples.get_Xs()
    trn_ys[0] = 1  # TODO

    clf = get_classifier(model_name, model_param)
    clf.fit(trn_Xs, trn_ys)
    tst_ys_pred = clf.predict(tst_Xs)
    tst_ys_pred[0] = 1  # TODO
    tst_ys_pred[1] = 1  # TODO

    for i, sample in enumerate(tst_samples):
        sample.set_y_pred(tst_ys_pred[i])


def gen_metrics(samples, filename):
    '''
    计算各项评价指标

    Args:
        samples (Samples): 已预测的测试样本
        filename (str): 结果文件
    '''
    ys = samples.get_ys()
    ys_pred = samples.get_ys_pred()
    metrics = [get_metric(metricname) for metricname in cf.metricNames]
    with open(filename, 'w') as outfile:
        for metric in metrics:
            ret = metric.get(ys, ys_pred)
            ret = metric.format(ret)
            outfile.write('%s\n' % ret)


def backTest():
    '''
    回测
    '''
    # 读入贷款协议数据，交易流水数据和签约产品数据
    reader = CMSBReader(cf.fieldName2fieldType)

    trnFeatLoanFilenames = [os.path.join(cf.loanDir, month) for month in cf.trnFeatMonths]
    trnFeatTransFilenames = [os.path.join(cf.transDir, month) for month in cf.trnFeatMonths]
    trnFeatProdFilenames = [os.path.join(cf.prodDir, month) for month in cf.trnFeatMonths]
    trnLabelLoanFilenames = [os.path.join(cf.loanDir, month) for month in cf.trnLabelMonths]
    tstFeatLoanFilenames = [os.path.join(cf.loanDir, month) for month in cf.tstFeatMonths]
    tstFeatTransFilenames = [os.path.join(cf.transDir, month) for month in cf.tstFeatMonths]
    tstFeatProdFilenames = [os.path.join(cf.prodDir, month) for month in cf.tstFeatMonths]
    tstLabelLoanFilenames = [os.path.join(cf.loanDir, month) for month in cf.tstLabelMonths]

    loanFieldName2Index, trnFeatLoans, trnFeatCustNum2ProtolNums = reader.readLoans(trnFeatLoanFilenames)
    transFieldName2Index, trnFeatTranss = reader.readTranss(trnFeatTransFilenames)
    prodFieldName2Index, trnFeatProds = reader.readProds(trnFeatProdFilenames)
    loanFieldName2Index, trnLabelLoans, trnLabelCustNum2ProtolNums = reader.readLoans(trnLabelLoanFilenames)
    loanFieldName2Index, tstFeatLoans, tstFeatCustNum2ProtolNums = reader.readLoans(tstFeatLoanFilenames)
    transFieldName2Index, tstFeatTranss = reader.readTranss(tstFeatTransFilenames)
    prodFieldName2Index, tstFeatProds = reader.readProds(tstFeatProdFilenames)
    loanFieldName2Index, tstLabelLoans, tstLabelCustNum2ProtolNums = reader.readLoans(tstLabelLoanFilenames)

    # 过滤贷款协议数据
    trnFeatLoans = filterLoans(cf.filterNames, loanFieldName2Index, trnFeatLoans, trnFeatCustNum2ProtolNums)
    tstFeatLoans = filterLoans(cf.filterNames, loanFieldName2Index, tstFeatLoans, tstFeatCustNum2ProtolNums)

    # ----------------------------------------------------------------------
    # 生成样本
    trn_samples_builder = SamplesBuilder(loanFieldName2Index, trnFeatLoans, trnFeatCustNum2ProtolNums, trnLabelLoans,
                                         transFieldName2Index, trnFeatTranss, prodFieldName2Index, trnFeatProds)
    tst_samples_builder = SamplesBuilder(loanFieldName2Index, tstFeatLoans, tstFeatCustNum2ProtolNums, tstLabelLoans,
                                         transFieldName2Index, tstFeatTranss, prodFieldName2Index, tstFeatProds)
    trn_samples = trn_samples_builder.buildSample()
    tst_samples = tst_samples_builder.buildSample()

    # ----------------------------------------------------------------------
    # 训练模型并预测
    fit_predict(cf.modelName, cf.modelParam, trn_samples, tst_samples)

    # 保存样本
    trn_samples.save(cf.trnSampFilename)
    tst_samples.save(cf.tstSampFilename)

    # 分析样本
    analyze_samples(trn_samples, tst_samples, 20, cf.analyFilename)

    # 计算评价指标
    gen_metrics(tst_samples, cf.metricFilename)


# def predict():
#     '''
#     预测
#     '''
#     # 读入贷款协议数据，交易流水数据和签约产品数据
#     reader = CMSBReader(cf.fieldName2fieldType)
#
#     trnFeatLoanFilenames = [os.path.join(cf.loanDir, month) for month in cf.trnFeatMonths]
#     trnFeatTransFilenames = [os.path.join(cf.transDir, month) for month in cf.trnFeatMonths]
#     trnFeatProdFilenames = [os.path.join(cf.prodDir, month) for month in cf.trnFeatMonths]
#     trnLabelLoanFilenames = [os.path.join(cf.loanDir, month) for month in cf.trnLabelMonths]
#     tstFeatLoanFilenames = [os.path.join(cf.loanDir, month) for month in cf.tstFeatMonths]
#     tstFeatTransFilenames = [os.path.join(cf.transDir, month) for month in cf.tstFeatMonths]
#     tstFeatProdFilenames = [os.path.join(cf.prodDir, month) for month in cf.tstFeatMonths]
#
#     loanFieldName2Index, trnFeatLoans = reader.readLoans(trnFeatLoanFilenames)
#     transFieldName2Index, trnFeatTranss = reader.readTranss(trnFeatTransFilenames)
#     prodFieldName2Index, trnFeatProds = reader.readProds(trnFeatProdFilenames)
#     loanFieldName2Index, trnLabelLoans = reader.readLoans(trnLabelLoanFilenames)
#     loanFieldName2Index, tstFeatLoans = reader.readLoans(tstFeatLoanFilenames)
#     transFieldName2Index, tstFeatTranss = reader.readTranss(tstFeatTransFilenames)
#     prodFieldName2Index, tstFeatProds = reader.readProds(tstFeatProdFilenames)
#
#     # 过滤贷款协议数据
#     trnFeatLoans = filterLoans(loanFieldName2Index, trnFeatLoans)
#     tstFeatLoans = filterLoans(loanFieldName2Index, tstFeatLoans)
#
#     # 生成用户特征
#     trnFeats = genFeats(loanFieldName2Index, trnFeatLoans,
#                         transFieldName2Index, trnFeatTranss,
#                         prodFieldName2Index, trnFeatProds)
#     tstFeats = genFeats(loanFieldName2Index, tstFeatLoans,
#                         transFieldName2Index, tstFeatTranss,
#                         prodFieldName2Index, tstFeatProds)
#
#     # 生成用户标签
#     trnLabels = genLabels(loanFieldName2Index, trnFeatLoans, trnLabelLoans)
#
#     # 训练模型并预测
#     clf = getClassifier(cf.modelName, cf.modelParam)
#     fit_model(clf, trnFeats, trnLabels)
#     tstLabelsPred = predictLabels(clf, tstFeats)
#
#     # 保存样本
#     saveSamples(trnFeats, trnLabels, cf.trnSampFilename)
#     saveSamples(tstFeats, tstLabelsPred, cf.tstSampFilename)


if __name__ == '__main__':

    backTest()
