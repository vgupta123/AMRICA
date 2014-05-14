#!/usr/bin/env python
"""
Author: Naomi Saphra (nsaphra@jhu.edu)

Describes a class for building graphs of AMRs with disagreements hilighted.
"""

# TODO deal with constant name dupes
import networkx as nx
import amr_metadata
from amr_alignment import Amr2AmrAligner
from amr_alignment import default_aligner
from smatch import smatch
from collections import defaultdict
import pygraphviz as pgz
import copy
import ConfigParser
from pynlpl.formats.giza import GizaSentenceAlignment

GOLD_COLOR = 'blue'
TEST_COLOR = 'red'
DFLT_COLOR = 'black'

class SmatchGraph:
  def __init__(self, inst, rel1, rel2, \
    gold_inst, gold_rel1, gold_rel2, \
    match, const_map_fn=default_aligner.const_map_fn, prebuilt_tables=False):
    """
    Input:
      (inst, rel1, rel2) from test amr.get_triples2()
      (gold_inst, gold_rel1, gold_rel2) from gold amr.get_triples2()
      match from smatch
      const_map_fn picks the matched gold label for a test label
      prebuilt_tables if (gold_inst, gold_rel1, gold_rel2) from gold amr2dict()
    """
    (self.inst, self.rel1, self.rel2) = (inst, rel1, rel2)
    if prebuilt_tables:
      (self.gold_inst_t, self.gold_rel1_t, self.gold_rel2_t) = \
        (gold_inst, gold_rel1, gold_rel2)
    else:
      (self.gold_inst_t, self.gold_rel1_t, self.gold_rel2_t) = \
        amr2dict(gold_inst, gold_rel1, gold_rel2)
    self.match = match
    self.map_fn = const_map_fn

    (self.unmatched_inst, self.unmatched_rel1, self.unmatched_rel2) = \
      [copy.deepcopy(x) for x in (self.gold_inst_t, self.gold_rel1_t, self.gold_rel2_t)]
    self.gold_ind = {} # test variable name -> gold variable index
    self.G = nx.MultiDiGraph()

  def smatch2graph(self):
    """
    Returns graph of test AMR / gold AMR union, with hilighted disagreements for
    different labels on edges and nodes, unmatched nodes and edges.
    """

    for (ind, (i, v, instof)) in enumerate(self.inst):
      self.gold_ind[v] = self.match[ind]

      node_color = DFLT_COLOR
      font_color = DFLT_COLOR
      label = instof
      if self.match[ind] < 0:
        font_color = TEST_COLOR
        node_color = TEST_COLOR
      else:
        if self.gold_inst_t[self.match[ind]] != instof:
          font_color = TEST_COLOR
          label = "%s (%s)" % (instof, self.gold_inst_t[self.match[ind]])
        if self.match[ind] in self.unmatched_inst:
          del self.unmatched_inst[self.match[ind]]
      self.G.add_node(v, label=label, color=node_color, font_color=font_color)

    # TODO decision: color all consts appearing in both charts black OR
    #      have consts hashed according to parent
    # TODO either expand the number of possible const matches
    #      or switch to a word-alignment-variant model
    for (reln, v, const) in self.rel1:
      node_color = DFLT_COLOR
      edge_color = DFLT_COLOR
      label = const
      const_match = self.map_fn(const)
      if (self.gold_ind[v], const_match) in self.gold_rel1_t:
        if const != const_match:
          label = "%s (%s)" % (const, const_match)
        if reln not in self.gold_rel1_t[(self.gold_ind[v], const_match)]:
          edge_color = TEST_COLOR

          # relns between existing nodes should be in unmatched rel2
          self.gold_ind[const] = const_match
          self.unmatched_rel2[(self.gold_ind[v], const_match)] = self.unmatched_rel1[(self.gold_ind[v], const_match)]
          del self.unmatched_rel1[(self.gold_ind[v], const_match)]
        else:
          self.unmatched_rel1[(self.gold_ind[v], const_match)].remove(reln)
      else:
        node_color = TEST_COLOR
        edge_color = TEST_COLOR
      # special case: "TOP" specifier not annotated
      if reln == 'TOP':
        # find similar TOP edges in gold if they are not labeled with same instance
        if edge_color == TEST_COLOR:
          for ((v_, c_), r_) in self.unmatched_rel1.items():
            if v_ == self.gold_ind[v] and 'TOP' in r_:
              edge_color = DFLT_COLOR
              self.unmatched_rel1[(v_, c_)].remove('TOP')
        self.G.add_edge(v, v, label=reln, color=edge_color, font_color=edge_color)
        continue
      self.G.add_node(v+' '+const, label=label, color=node_color, font_color=node_color)
      self.G.add_edge(v, v+' '+const, label=reln, color=edge_color, font_color=edge_color)

    for (reln, v1, v2) in self.rel2:
      edge_color = DFLT_COLOR
      if (self.gold_ind[v1], self.gold_ind[v2]) in self.gold_rel2_t:
        if reln not in self.gold_rel2_t[(self.gold_ind[v1], self.gold_ind[v2])]:
          edge_color = TEST_COLOR
        else:
          self.unmatched_rel2[(self.gold_ind[v1], self.gold_ind[v2])].remove(reln)
      else:
        edge_color = TEST_COLOR
      self.G.add_edge(v1, v2, label=reln, color=edge_color, font_color=edge_color)

    # Add gold standard elements not in test
    node_hashes = {v:k for (k,v) in self.gold_ind.items()} # reverse lookup from gold ind
    for (self.gold_ind, instof) in self.unmatched_inst.items():
      node_hashes[self.gold_ind] = 'GOLD %s' % self.gold_ind
      self.G.add_node(node_hashes[self.gold_ind], label=instof, color=GOLD_COLOR, font_color=GOLD_COLOR)
    for ((self.gold_ind, const), relns) in self.unmatched_rel1.items():
      #TODO check if const node already in
      for reln in relns:
        # special case: "TOP" specifier not annotated
        if reln == 'TOP':
          self.G.add_edge(node_hashes[self.gold_ind], node_hashes[self.gold_ind], label=reln, color=GOLD_COLOR, font_color=GOLD_COLOR)
          continue

        const_hash = node_hashes[self.gold_ind] + ' ' + const
        if const_hash not in node_hashes:
          node_hashes[const_hash] = const_hash
          self.G.add_node(const_hash, label=const, color=GOLD_COLOR, font_color=GOLD_COLOR)
        self.G.add_edge(node_hashes[self.gold_ind], node_hashes[const_hash], label=reln, color=GOLD_COLOR, font_color=GOLD_COLOR)
    for ((self.gold_ind1, self.gold_ind2), relns) in self.unmatched_rel2.items():
      for reln in relns:
        self.G.add_edge(node_hashes[self.gold_ind1], node_hashes[self.gold_ind2], label=reln, color=GOLD_COLOR, font_color=GOLD_COLOR)
    return self.G


def amr2dict(inst, rel1, rel2):
  """ Get tables of AMR data indexed by variable number """
  node_inds = {}
  inst_t = {}
  for (ind, (i, v, label)) in enumerate(inst):
    node_inds[v] = ind
    inst_t[ind] = label

  rel1_t = {}
  for (label, v1, const) in rel1:
    if (node_inds[v1], const) not in rel1_t:
      rel1_t[(node_inds[v1], const)] = set()
    rel1_t[(node_inds[v1], const)].add(label)

  rel2_t = {}
  for (label, v1, v2) in rel2:
    if (node_inds[v1], node_inds[v2]) not in rel2_t:
      rel2_t[(node_inds[v1], node_inds[v2])] = set()
    rel2_t[(node_inds[v1], node_inds[v2])].add(label)

  return (inst_t, rel1_t, rel2_t)


