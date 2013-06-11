#! /usr/bin/env python

import math, sys, copy, exceptions, array
sys.argv.append('-b')

import ROOT
ROOT.gROOT.SetStyle("Plain")
ROOT.gStyle.SetOptStat(000000000)
ROOT.gStyle.SetOptTitle(0)

import style
from ROOT import TCanvas, TFile, TH1, THStack, TLegend

class hinfo:

    def __init__(self, name):

        fields = name.split('__')
        self.channel = fields[0]
        self.process = fields[1]
        self.systematic = None
        self.shift = None
        if len(fields) > 2:
            self.systematic = fields[2]
            self.shift = fields[3]


def name(channel, process, systematic = None, shift = None):
    if not systematic:
        return '__'.join([channel, process])
    return '__'.join([channel, process, systematic, shift])


def merge(old, new):
    if not old:
        old = new.Clone()
    else:
        old.Add(new)
    return old



class PropagateShapeSystematics:


    def __init__(self, filename, scales = {}, rebin = None):
        file = TFile(filename)
        keys = file.GetListOfKeys()
        self.histograms = {}
        self.channels = []
        self.method = 'NormalApproximation'
        for key in keys:
            key = key.GetName()
            self.histograms[key] = copy.copy(file.Get(key).Clone())
            info = hinfo(key)
            if info.process in scales:
                print 'Scaling histogram %s by %0.3f' % (key, scales[info.process])
                self.histograms[key].Scale(scales[info.process])
            if rebin:
                self.histograms[key].Rebin(rebin)
            if not info.channel in self.channels:
                self.channels.append(info.channel) 


    def set_method(self, method):
        if method in ['NormalApproximation', 'LogNormalApproximation']:
            self.method = method


    def get_process(self, channel, process):
        return self.histograms[name(channel, process)]


    def get_background(self, channel, processes, systematics, tolerance = 0.10):
        # Loop first over the nominal distributions
        h_nominal = None

        for process in processes:
            h_nominal = merge(h_nominal, self.histograms[name(channel,process)])

        # Loop over the shape systematics computing location and scale 
        parameters = {}
        for systematic in systematics:
            h_plus = None
            h_minus = None
            # Mergin systematic histograms
            for process in processes:
                if name(channel,process,systematic,'plus') in self.histograms:
                    h_plus = merge(h_plus, self.histograms[name(channel,process,systematic,'plus')])            
                    h_minus = merge(h_minus, self.histograms[name(channel,process,systematic,'minus')])             
                else:
                    h_plus = merge(h_plus, self.histograms[name(channel,process)])       
                    h_minus = merge(h_minus, self.histograms[name(channel,process)])
            # Computing mu and sigma2
            parameters[systematic] = h_nominal.Clone()
            for i in range(h_nominal.GetNbinsX()):
                if self.method == 'NormalApproximation':
                    plus = 0
                    if h_plus.GetBinContent(i+1) != 0 and \
                      (h_plus.GetBinError(i+1)/h_plus.GetBinContent(i+1)) < tolerance:  
                        plus = h_plus.GetBinContent(i+1) - h_nominal.GetBinContent(i+1)
                    minus = 0
                    if h_minus.GetBinContent(i+1) != 0 and \
                      (h_minus.GetBinError(i+1)/h_minus.GetBinContent(i+1)) < tolerance:                  
                        minus = h_minus.GetBinContent(i+1) - h_nominal.GetBinContent(i+1)
                    mu = (plus+minus)/3
                    sigma2 = ((plus - mu)**2 + mu**2 + (minus - mu)**2)/2
                    parameters[systematic].SetBinContent(i+1, mu)
                    parameters[systematic].SetBinError(i+1, sigma2)
                elif self.method == 'LogNormalApproximation':
                    plus = 1.0
                    if h_plus.GetBinContent(i+1) != 0 and \
                      (h_plus.GetBinError(i+1)/h_plus.GetBinContent(i+1)) < tolerance:
                        plus = h_plus.GetBinContent(i+1)/h_nominal.GetBinContent(i+1)
                    minus = 1.0
                    if h_minus.GetBinContent(i+1) != 0 and \
                      (h_minus.GetBinError(i+1)/h_minus.GetBinContent(i+1)) < tolerance:              
                        minus = h_minus.GetBinContent(i+1)/h_nominal.GetBinContent(i+1)
                    mu = (math.log(plus) + math.log(minus))/3
                    sigma2 = ((math.log(plus) - mu)**2 + mu**2 + (math.log(minus) - mu)**2)/2
                    parameters[systematic].SetBinContent(i+1, mu)
                    parameters[systematic].SetBinError(i+1, sigma2)                    
                else:
                    raise exceptions.RuntimeError('Unsuported approximation.')

        # Computing a combined average and std from all the systematics
        print 'Systematic shifts and errors'

        histogram = h_nominal.Clone() 
        x = array.array('d')
        y = array.array('d')
        exl = array.array('d')
        exh = array.array('d')
        eyl = array.array('d')
        eyh = array.array('d')
            
        for i in range(histogram.GetNbinsX()):
            value = 0 
            error2 = 0
            for systematic in parameters:
                value = value + parameters[systematic].GetBinContent(i+1)
                error2 = error2 + parameters[systematic].GetBinError(i+1)
            if self.method == 'NormalApproximation':
                histogram.SetBinContent(i+1, h_nominal.GetBinContent(i+1) + value)
                histogram.SetBinError(i+1, math.sqrt(h_nominal.GetBinError(i+1)**2 + error2))
                print '  %d-%d shift %0.2f%% error %0.2f%%' % (
                    histogram.GetXaxis().GetBinLowEdge(i+1),
                    histogram.GetXaxis().GetBinLowEdge(i+1) + histogram.GetXaxis().GetBinWidth(i+1),
                    100*(histogram.GetBinContent(i+1)-h_nominal.GetBinContent(i+1))/h_nominal.GetBinContent(i+1),
                    100*histogram.GetBinError(i+1)/h_nominal.GetBinContent(i+1)
                )
            elif self.method == 'LogNormalApproximation':
                plus = (h_nominal.GetBinContent(i+1)+h_nominal.GetBinError(i+1))/h_nominal.GetBinContent(i+1)
                minus = (h_nominal.GetBinContent(i+1)-h_nominal.GetBinError(i+1))/h_nominal.GetBinContent(i+1)
                mu = (math.log(plus) + math.log(minus))/3 
                sigma2 = ((math.log(plus) - mu)**2 + mu**2 + (math.log(minus) - mu)**2)/2
                value = value + mu
                error2 = error2 + sigma2
                x.append(histogram.GetXaxis().GetBinCenter(i+1))
                y.append(h_nominal.GetBinContent(i+1) * math.exp(value))
                exl.append(histogram.GetXaxis().GetBinWidth(i+1)/2)
                exh.append(histogram.GetXaxis().GetBinWidth(i+1)/2)
                eyl.append(h_nominal.GetBinContent(i+1)*(math.exp(value - math.sqrt(error2))-math.exp(value)))
                eyh.append(h_nominal.GetBinContent(i+1)*(math.exp(value + math.sqrt(error2))-math.exp(value)))
                print '  %d-%d shift %0.2f%% error +%0.2f%% %0.2f%% ' % (
                    histogram.GetXaxis().GetBinLowEdge(i+1),
                    histogram.GetXaxis().GetBinLowEdge(i+1) + histogram.GetXaxis().GetBinWidth(i+1),
                    100*(math.exp(value)-1.0),
                    100*(math.exp(value + math.sqrt(error2))-math.exp(value)),
                    100*(math.exp(value - math.sqrt(error2))-math.exp(value))
                )

        if self.method == 'LogNormalApproximation':
            histogram = ROOT.TGraphAsymmErrors(len(x), x, y, exl, exh, eyl, eyh) 
        
        return histogram


def plot(filename, xtitle, systematics):

    scales = {
        'wlight': 0.969941983946,
        'wc': 1.29236852278,
        'wb': 0.805940129994,
        'zlight': 0.722795896298,
        'diboson': 1.0430264982,
        'ttbar': 0.89201585547,
        'singletop': 1.76216704736
    }

    channel_to_label = {
        'el_0btag_mttbar': 'e+jets, N_{b-tag} = 0',
        'el_1btag_mttbar': 'e+jets, N_{b-tag} #geq 1',
        'mu_0btag_mttbar': '#mu+jets, N_{b-tag} = 0',
        'mu_1btag_mttbar': '#mu+jets, N_{b-tag} #geq 1'
    }

    backgrounds = ['ttbar', 'wlight', 'wc', 'wb', 'zlight', 'singletop', 'diboson']    

    root_style = style.analysis()
    root_style.cd()
    canvas = TCanvas('canvas', 'canvas', 600, 600)
    canvas.Divide(1,2)

    propagator = PropagateShapeSystematics(filename, scales)
    propagator.set_method('LogNormalApproximation')

    # loop over all the propagated channels
    for channel in sorted(propagator.channels):

        print "Systematics for channel %s" % channel

        h_bkg = propagator.get_background(channel, backgrounds, systematics)
        h_bkg.SetLineColor(ROOT.kGray+1)
        h_bkg.SetFillColor(ROOT.kGray+1)
        h_sys = h_bkg.Clone()
        #h_sys.SetLineColor(ROOT.kBlack)
        h_sys.SetFillColor(ROOT.kBlack)
        h_sys.SetFillStyle(3345)

        h_data = propagator.get_process(channel, 'DATA')
        h_data.SetLineColor(ROOT.kBlack)  
        h_data.SetMarkerStyle(20)

        pad = canvas.cd(1)
        pad.SetPad(0, 0.3, 1, 1)
        pad.SetLogy()
        pad.SetLeftMargin(0.15)
        pad.SetBottomMargin(0.15)
        
        maxs = [h_data.GetMaximum(), h_bkg.GetMaximum()]
        h_data.GetYaxis().SetRangeUser(0.5,max(maxs)*5)
        h_data.GetYaxis().SetLabelSize(0.05)
        h_data.GetYaxis().SetTitleSize(0.06)
        h_data.GetYaxis().SetTitleOffset(1.3)
        h_data.GetYaxis().SetTitleFont(62)
        h_data.GetYaxis().SetNdivisions(5)
        h_data.GetYaxis().SetTitle('event yield')
        h_data.GetXaxis().SetLabelSize(0.05)
        h_data.GetXaxis().SetTitleSize(0.06)
        h_data.GetXaxis().SetTitleFont(62)
        h_data.GetXaxis().SetNdivisions(5)
        h_data.GetXaxis().SetTitle(xtitle)

        h_data.Draw('e')
        #h_bkg.Draw('B')
        h_sys.Draw('2')
        #h_data.Draw('samee')

        legend = TLegend(.65, .75, .95, .88)
        legend.SetBorderSize(0);
        legend.AddEntry(h_bkg, "background", "fe")
        legend.AddEntry(h_sys, "Uncertainty", "fe")
        legend.AddEntry(h_data, "CMS Data 2012", "lpe")
        legend.Draw()

        labelcms = TLegend(.15, .91, 1, .96)
        labelcms.SetMargin(0.12);
        labelcms.SetFillColor(10);
        labelcms.SetBorderSize(0);
        labelcms.SetHeader('CMS Preliminary, 19.6 fb^{-1},  #sqrt{s} = 8 TeV')
        labelcms.Draw()

        labellumi2 = TLegend(.67, .48, .95, .53)
        labellumi2.SetMargin(0.12);
        labellumi2.SetFillColor(10);
        labellumi2.SetBorderSize(0);
        labellumi2.SetHeader(channel_to_label[channel])
        labellumi2.Draw()

        pad = canvas.cd(2)
        pad.SetPad(0, 0, 1, 0.3)
        pad.SetLeftMargin(0.15)
        pad.SetBottomMargin(0.15)
 
        canvas.Update()
        canvas.SaveAs('h_'+filename.split('.')[0]+'_'+channel+'.png')        
        sys.exit(1)
       
        h_ratio = h_data.Clone()
        h_error = h_data.Clone()

        h_ratio.Divide(h_bkg)
        for i in range(h_ratio.GetNbinsX()):
            h_error.SetBinContent(i+1,1.0)
            if h_bkg.GetBinContent(i+1) > 0:
                h_error.SetBinError(i+1,h_bkg.GetBinError(i+1)/h_bkg.GetBinContent(i+1))
                h_ratio.SetBinError(i+1,h_data.GetBinError(i+1)/h_bkg.GetBinContent(i+1))
            else:
                h_error.SetBinError(i+1, 0.0)
        h_ratio.GetYaxis().SetRangeUser(0,2)
        h_error.SetMarkerSize(0)
        h_error.SetLineWidth(2)
        h_error.SetLineColor(ROOT.kGray)
        h_error.SetFillStyle(1001)
        h_error.SetFillColor(ROOT.kGray)
        
        h_ratio.GetXaxis().SetTitle('')
        h_ratio.GetXaxis().SetLabelSize(2*h_ratio.GetXaxis().GetLabelSize())
        h_ratio.GetYaxis().SetTitle('data / bkg')
        h_ratio.GetYaxis().SetTitleSize(2*h_ratio.GetYaxis().GetTitleSize())
        h_ratio.GetYaxis().SetTitleOffset(0.5*h_ratio.GetYaxis().GetTitleOffset())
        h_ratio.GetYaxis().SetLabelSize(2*h_ratio.GetYaxis().GetLabelSize())
        h_ratio.SetMinimum(0.0)   
        h_ratio.SetMaximum(2.0)        

        h_ratio.Draw('9')
        h_error.Draw('9 same e2')
        h_ratio.Draw('9 same')

        canvas.Update()
        canvas.SaveAs('h_'+filename.split('.')[0]+'_'+channel+'.png')

        
plot('boosted_semileptonic_lepton_rebinned.root',  
     'M_{t#bar{t}} [GeV/c^{2}]',
     ['btageff'] 
     #['bmistag', 'btageff', 'jec', 'jer', 'matching_vjets', 'muonid', 'pdf', 'scale_ttbar', 'scale_vjets']
)


