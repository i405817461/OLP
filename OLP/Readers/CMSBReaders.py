# -*- coding: utf-8 -*-

from OLP.Readers.ReaderTools import UniPrinter
from OLP.Readers.Reader import Reader


class CMSBFieldProcessor(object):

    def __init__(self, fieldName2fieldType):
        self.fieldName2fieldType = fieldName2fieldType
        self.loanFieldName2IndexOld = {}
        self.loanFieldName2IndexNew = {}
        self.transFieldName2IndexOld = {}
        self.transFieldName2IndexNew = {}
        self.prodFieldName2IndexOld = {}
        self.prodFieldName2IndexNew = {}

    def buildLoanFieldNameIndex(self, fieldNames):
        return self.buildIndex(fieldNames, self.loanFieldName2IndexOld, self.loanFieldName2IndexNew)

    def buildTransFieldNameIndex(self, fieldNames):
        return self.buildIndex(fieldNames, self.transFieldName2IndexOld, self.transFieldName2IndexNew)

    def buildProdFieldNameIndex(self, fieldNames):
        return self.buildIndex(fieldNames, self.prodFieldName2IndexOld, self.prodFieldName2IndexNew)

    def buildIndex(self, fieldNames, fieldName2IndexOld, fieldName2IndexNew):
        fieldName2IndexOld.clear()
        fieldName2IndexNew.clear()
        for fieldName in fieldNames:
            fieldName2IndexOld[fieldName] = len(fieldName2IndexOld)
            if fieldName in self.fieldName2fieldType:  # 保留目标字段
                fieldName2IndexNew[fieldName] = len(fieldName2IndexNew)
        return fieldName2IndexNew

    def convertLoanFields(self, fields):
        return self.convert(fields, self.loanFieldName2IndexOld, self.loanFieldName2IndexNew)

    def convertTransFields(self, fields):
        return self.convert(fields, self.transFieldName2IndexOld, self.transFieldName2IndexNew)

    def convertProdFields(self, fields):
        return self.convert(fields, self.prodFieldName2IndexOld, self.prodFieldName2IndexNew)

    def convert(self, fields, fieldName2IndexOld, fieldName2IndexNew):
        fieldsCnvtd = [0.0] * len(fieldName2IndexNew)
        for fieldName in fieldName2IndexNew:
            type_ = self.fieldName2fieldType[fieldName]
            indexOld = fieldName2IndexOld[fieldName]
            indexNew = fieldName2IndexNew[fieldName]
            #print len(fieldName2IndexNew), len(fieldName2IndexOld)
            #print fieldName
            #print len(fieldsCnvtd), indexNew, len(fields), indexOld
            fieldsCnvtd[indexNew] = type_(fields[indexOld])
        return fieldsCnvtd

    def addLoanFields(self, fields, samples, primFieldName):
        self.addFields(fields, samples, primFieldName, self.loanFieldName2IndexNew)

    def addTransFields(self, fields, samples, primFieldName):
        self.addFields(fields, samples, primFieldName, self.transFieldName2IndexNew)

    def addProdFields(self, fields, samples, primFieldName):
        self.addFields(fields, samples, primFieldName, self.prodFieldName2IndexNew)

    def addFields(self, fields, samples, primFieldName, fieldName2Index):
        primFieldIndex = fieldName2Index[primFieldName]
        primField = fields[primFieldIndex]

        if primField not in samples:
            sample = []
            for j, field in enumerate(fields):
                sample.append([])
                sample[j].append(field)
            samples[primField] = sample
        else:
            sample = samples[primField]
            for j, field in enumerate(fields):
                sample[j].append(field)

    def expandSamples(self, samples, primFieldName, fieldName2Index):
        dimMax = 0
        for sample in samples.itervalues():
            for field in sample:
                dimMax = max(dimMax, len(field))
        for sample in samples.itervalues():
            for fieldName, fieldIndex in fieldName2Index.iteritems():
                field = sample[fieldIndex]
                if len(field) < dimMax:
                    type_ = self.fieldName2fieldType[fieldName]
                    sample[fieldIndex] = [type_()] * (dimMax - len(field))
                    sample[fieldIndex].extend(field)
        return samples


class CMSBReader(Reader):

    def __init__(self, fieldName2fieldType):
        self.fieldProcessor = CMSBFieldProcessor(fieldName2fieldType)
        self.protolNumName = '协议号'
        self.custNumName = '我行客户号'

    def readLoans(self, filenames):
        fieldName2Index = {}
        loans = {}

        for i, filename in enumerate(filenames):
            with open(filename) as inFile:
                # 读取第一行
                firstLine = inFile.readline()
                if i == 0:  # 第一次读取文件
                    fieldNames = firstLine.strip().split('\t')  # 利用第一行获取所有字段
                    fieldName2Index = self.fieldProcessor.buildLoanFieldNameIndex(fieldNames)  # 构建字段索引
                # 读取剩余行，获取各字段对应数据
                for line in inFile:
                    fields = line.strip().split('\t')
                    fields = self.fieldProcessor.convertLoanFields(fields)
                    self.fieldProcessor.addLoanFields(fields, loans, self.protolNumName)
                inFile.close()
        loans = self.fieldProcessor.expandSamples(loans, self.protolNumName, fieldName2Index)  # 扩展字段维数

        return fieldName2Index, loans

    def readTranss(self, filenames):
        fieldName2Index = {}
        transs = {}

        for i, filename in enumerate(filenames):
            with open(filename) as inFile:
                # 读取第一行
                firstLine = inFile.readline()
                if i == 0:  # 第一次读取文件
                    fieldNames = firstLine.strip().split('\t')  # 第一次读取，利用第一行获取所有字段
                    fieldName2Index = self.fieldProcessor.buildTransFieldNameIndex(fieldNames)  # 构建字段索引
                # 读取剩余行，获取各字段对应数据
                for line in inFile:
                    fields = line.strip().split('\t')
                    fields = self.fieldProcessor.convertTransFields(fields)
                    self.fieldProcessor.addTransFields(fields, transs, self.custNumName)
                inFile.close()

        return fieldName2Index, transs

    def readProds(self, filenames):
        fieldName2Index = {}
        prods = {}

        for i, filename in enumerate(filenames):
            with open(filename) as inFile:
                # 读取第一行
                firstLine = inFile.readline()
                if i == 0:  # 第一次读取文件
                    fieldNames = firstLine.strip().split('\t')  # 第一次读取，利用第一行获取所有字段
                    fieldName2Index = self.fieldProcessor.buildProdFieldNameIndex(fieldNames)  # 构建字段索引
                # 读取剩余行，获取各字段对应数据
                for line in inFile:
                    fields = line.strip().split('\t')
                    fields = self.fieldProcessor.convertProdFields(fields)
                    self.fieldProcessor.addProdFields(fields, prods, self.custNumName)
                inFile.close()

        return fieldName2Index, prods
