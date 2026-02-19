from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime
from statistics import mean, pstdev
from typing import Dict, Iterable, List, Optional, Set, Tuple
import logging

import networkx as nx

from .config import settings
from .schemas import (
    AnalysisResult,
    FraudRing,
    GraphData,
    GraphEdge,
    GraphNode,
    Summary,
)


logger = logging.getLogger("money_muling_analysis")


@dataclass
class Transaction:
    transaction_id: str
    sender_id: str
    receiver_id: str
    amount: float
    timestamp: datetime


def build_graph(transactions: Iterable[Transaction]) -> nx.DiGraph:
    g = nx.DiGraph()
    for tx in transactions:
        g.add_node(tx.sender_id)
        g.add_node(tx.receiver_id)
        g.add_edge(
            tx.sender_id,
            tx.receiver_id,
            transaction_id=tx.transaction_id,
            amount=tx.amount,
            timestamp=tx.timestamp,
        )
    return g


def _canonical_ring_key(members: Iterable[str]) -> Tuple[str, ...]:
    return tuple(sorted(set(members)))


def detect_cycle_rings(g: nx.DiGraph) -> Dict[Tuple[str, ...], FraudRing]:
    """
    Detect directed cycles of length 3–5 using bounded-depth DFS restricted to SCCs.

    Steps (per requirements):
    - Remove nodes with total degree < 2.
    - Compute SCCs on the remaining graph.
    - Run cycle detection only inside SCCs with size in [3, 100].
    - DFS depth bounded to 5, no revisits in current path.
    - Deduplicate cycles via canonical node-set key.
    """
    total_nodes = g.number_of_nodes()
    total_edges = g.number_of_edges()

    # Remove nodes with total degree < 2
    nodes_to_keep = [
        n for n in g.nodes if g.in_degree(n) + g.out_degree(n) >= 2
    ]
    sub = g.subgraph(nodes_to_keep).copy()

    # Compute SCCs
    sccs = list(nx.strongly_connected_components(sub))
    scc_count = len(sccs)
    largest_scc_size = max((len(c) for c in sccs), default=0)

    logger.info(
        "Graph stats: total_nodes=%d total_edges=%d scc_count=%d largest_scc_size=%d",
        total_nodes,
        total_edges,
        scc_count,
        largest_scc_size,
    )

    rings: Dict[Tuple[str, ...], FraudRing] = {}
    max_depth = 5  # maximum path length in nodes

    def dfs(start: str, current: str, path: List[str], local_sub: nx.DiGraph):
        # Prune if depth exceeded
        if len(path) > max_depth:
            return

        # If current node has no outgoing edges, prune
        if local_sub.out_degree(current) == 0:
            return

        for nbr in local_sub.successors(current):
            if nbr == start:
                # Possible cycle
                cycle_length = len(path)
                if 3 <= cycle_length <= 5:
                    key = _canonical_ring_key(path)
                    if key not in rings:
                        # Simple risk score: base on length
                        risk = min(100.0, 70.0 + (len(key) - 3) * 10.0)
                        ring_id = f"RING_CYCLE_{len(rings) + 1:03d}"
                        rings[key] = FraudRing(
                            ring_id=ring_id,
                            member_accounts=list(key),
                            pattern_type="cycle",
                            risk_score=risk,
                        )
                # Do not continue from start again
                continue

            if nbr in path:
                # Avoid revisiting nodes in current path
                continue

            # DFS pruning: if even with remaining depth we cannot reach min cycle length (3),
            # we would prune here. With max_depth=5 and starting from length>=1, this condition
            # is always satisfiable for cycles of length 3, so no extra pruning is required.
            new_path = path + [nbr]
            dfs(start, nbr, new_path, local_sub)

    # Run DFS only within SCCs of size between 3 and 100
    for comp in sccs:
        size = len(comp)
        if size < 3 or size > 100:
            continue
        local_sub = sub.subgraph(comp).copy()
        for node in local_sub.nodes:
            dfs(node, node, [node], local_sub)

    logger.info("Cycle detection: unique_cycles=%d", len(rings))
    return rings


def _group_transactions_by_account(
    transactions: Iterable[Transaction],
) -> Tuple[Dict[str, List[Transaction]], Dict[str, List[Transaction]]]:
    by_sender: Dict[str, List[Transaction]] = defaultdict(list)
    by_receiver: Dict[str, List[Transaction]] = defaultdict(list)
    for tx in transactions:
        by_sender[tx.sender_id].append(tx)
        by_receiver[tx.receiver_id].append(tx)
    for tx_list in by_sender.values():
        tx_list.sort(key=lambda t: t.timestamp)
    for tx_list in by_receiver.values():
        tx_list.sort(key=lambda t: t.timestamp)
    return by_sender, by_receiver


def _account_stats(
    by_sender: Dict[str, List[Transaction]],
    by_receiver: Dict[str, List[Transaction]],
) -> Dict[str, Dict[str, float]]:
    stats: Dict[str, Dict[str, float]] = {}
    accounts: Set[str] = set(by_sender.keys()) | set(by_receiver.keys())
    for acc in accounts:
        txs = by_sender.get(acc, []) + by_receiver.get(acc, [])
        if not txs:
            continue
        amounts = [t.amount for t in txs]
        timestamps = [t.timestamp for t in txs]
        timestamps.sort()
        tx_count = len(txs)
        avg_amt = mean(amounts)
        if len(amounts) > 1 and avg_amt > 0:
            cv = pstdev(amounts) / avg_amt
        else:
            cv = 0.0
        span_days = (timestamps[-1] - timestamps[0]).days or 0
        stats[acc] = {
            "tx_count": tx_count,
            "amount_cv": cv,
            "span_days": span_days,
        }
    return stats


def _is_likely_merchant(stats: Dict[str, float]) -> bool:
    return (
        stats["tx_count"] >= settings.MERCHANT_TX_COUNT_THRESHOLD
        and stats["amount_cv"] <= settings.MERCHANT_AMOUNT_CV_THRESHOLD
        and stats["span_days"] >= settings.MERCHANT_MIN_OBSERVATION_DAYS
    )


def _is_likely_payroll(
    account_id: str,
    by_sender: Dict[str, List[Transaction]],
    stats: Dict[str, float],
) -> bool:
    """
    Heuristic: many similar outgoing payments on multiple distinct pay dates.
    """
    if stats["tx_count"] < settings.PAYROLL_TX_COUNT_THRESHOLD:
        return False
    if stats["amount_cv"] > settings.PAYROLL_AMOUNT_CV_THRESHOLD:
        return False
    txs = by_sender.get(account_id, [])
    if len(txs) < settings.PAYROLL_TX_COUNT_THRESHOLD:
        return False
    pay_dates: Set[datetime.date] = {t.timestamp.date() for t in txs}
    return len(pay_dates) >= settings.PAYROLL_MIN_PAY_DATES


def detect_smurf_rings(
    transactions: Iterable[Transaction],
) -> Dict[Tuple[str, ...], FraudRing]:
    by_sender, by_receiver = _group_transactions_by_account(transactions)
    stats = _account_stats(by_sender, by_receiver)

    rings: Dict[Tuple[str, ...], FraudRing] = {}

    # Fan-in: many senders -> one receiver in window
    for receiver, txs in by_receiver.items():
        receiver_stats = stats.get(receiver)
        if receiver_stats and _is_likely_merchant(receiver_stats):
            # Do not flag classic merchant behavior
            continue
        window_start = 0
        counterparties: Dict[str, int] = defaultdict(int)
        for window_end, tx in enumerate(txs):
            counterparties[tx.sender_id] += 1
            while (
                tx.timestamp - txs[window_start].timestamp
                > settings.SMURF_WINDOW
            ):
                left = txs[window_start]
                counterparties[left.sender_id] -= 1
                if counterparties[left.sender_id] <= 0:
                    counterparties.pop(left.sender_id, None)
                window_start += 1
            if len(counterparties) >= settings.SMURF_MIN_COUNTERPARTIES:
                members = list(counterparties.keys()) + [receiver]
                key = _canonical_ring_key(members)
                if key not in rings:
                    ring_id = f"RING_FANIN_{len(rings) + 1:03d}"
                    risk = min(100.0, 75.0)
                    rings[key] = FraudRing(
                        ring_id=ring_id,
                        member_accounts=list(key),
                        pattern_type="fan_in",
                        risk_score=risk,
                    )

    # Fan-out: one sender -> many receivers in window
    for sender, txs in by_sender.items():
        sender_stats = stats.get(sender)
        if sender_stats and _is_likely_payroll(sender, by_sender, sender_stats):
            # Likely payroll, skip to avoid false positives
            continue
        window_start = 0
        counterparties = defaultdict(int)
        for window_end, tx in enumerate(txs):
            counterparties[tx.receiver_id] += 1
            while (
                tx.timestamp - txs[window_start].timestamp
                > settings.SMURF_WINDOW
            ):
                left = txs[window_start]
                counterparties[left.receiver_id] -= 1
                if counterparties[left.receiver_id] <= 0:
                    counterparties.pop(left.receiver_id, None)
                window_start += 1
            if len(counterparties) >= settings.SMURF_MIN_COUNTERPARTIES:
                members = list(counterparties.keys()) + [sender]
                key = _canonical_ring_key(members)
                if key not in rings:
                    ring_id = f"RING_FANOUT_{len(rings) + 1:03d}"
                    risk = min(100.0, 75.0)
                    rings[key] = FraudRing(
                        ring_id=ring_id,
                        member_accounts=list(key),
                        pattern_type="fan_out",
                        risk_score=risk,
                    )

    return rings


def detect_shell_rings(
    g: nx.DiGraph, transactions: Iterable[Transaction]
) -> Dict[Tuple[str, ...], FraudRing]:
    # Precompute total transaction count per account
    tx_counts: Dict[str, int] = defaultdict(int)
    for tx in transactions:
        tx_counts[tx.sender_id] += 1
        tx_counts[tx.receiver_id] += 1

    rings: Dict[Tuple[str, ...], FraudRing] = {}
    ring_index = 0

    # BFS depth limit (in edges)
    max_depth = 4

    for source in g.nodes:
        # Only start BFS from nodes with total transactions <= 3
        if tx_counts.get(source, 0) > settings.SHELL_MAX_INTERMEDIATE_TX_COUNT:
            continue

        queue: deque[List[str]] = deque()
        queue.append([source])
        visited_state: Set[Tuple[str, int]] = set()

        while queue:
            path = queue.popleft()
            hops = len(path) - 1
            if hops >= max_depth:
                continue

            last = path[-1]
            for neighbor in g.successors(last):
                if neighbor in path:
                    continue

                # If neighbor is an intermediate node (not terminal yet), enforce tx_count <= 3
                if tx_counts.get(neighbor, 0) > settings.SHELL_MAX_INTERMEDIATE_TX_COUNT:
                    # Stop this branch as soon as we hit a high-activity intermediate
                    continue

                new_path = path + [neighbor]
                new_hops = len(new_path) - 1
                state = (neighbor, new_hops)
                if state in visited_state:
                    continue
                visited_state.add(state)

                if new_hops >= settings.SHELL_MIN_HOPS:
                    intermediates = new_path[1:-1]
                    if intermediates and all(
                        tx_counts[n] <= settings.SHELL_MAX_INTERMEDIATE_TX_COUNT
                        for n in intermediates
                    ):
                        key = _canonical_ring_key(new_path)
                        if key not in rings:
                            ring_index += 1
                            risk = min(
                                100.0,
                                60.0 + len(intermediates)
                                * (settings.SCORE_SHELL / 2),
                            )
                            rings[key] = FraudRing(
                                ring_id=f"RING_SHELL_{ring_index:03d}",
                                member_accounts=list(key),
                                pattern_type="shell",
                                risk_score=risk,
                            )

                if new_hops < max_depth:
                    queue.append(new_path)

    return rings


def detect_high_velocity(
    transactions: Iterable[Transaction],
) -> Set[str]:
    by_account: Dict[str, List[datetime]] = defaultdict(list)
    for tx in transactions:
        by_account[tx.sender_id].append(tx.timestamp)
        by_account[tx.receiver_id].append(tx.timestamp)
    high_velocity_accounts: Set[str] = set()
    for acc, times in by_account.items():
        times.sort()
        window_start = 0
        for window_end, t in enumerate(times):
            while (
                t - times[window_start]
                > settings.HIGH_VELOCITY_WINDOW
            ):
                window_start += 1
            if (
                window_end - window_start + 1
                >= settings.HIGH_VELOCITY_THRESHOLD
            ):
                high_velocity_accounts.add(acc)
                break
    return high_velocity_accounts


def compute_scores_and_patterns(
    all_rings: Dict[Tuple[str, ...], FraudRing],
    high_velocity_accounts: Set[str],
) -> Tuple[Dict[str, float], Dict[str, Set[str]], Dict[str, List[str]]]:
    scores: Dict[str, float] = defaultdict(float)
    patterns: Dict[str, Set[str]] = defaultdict(set)
    account_rings: Dict[str, List[str]] = defaultdict(list)

    for members, ring in all_rings.items():
        for acc in members:
            if ring.pattern_type == "cycle":
                scores[acc] += settings.SCORE_CYCLE
                patterns[acc].add(f"cycle_length_{len(members)}")
            elif ring.pattern_type == "fan_in":
                scores[acc] += settings.SCORE_FAN_IN
                patterns[acc].add("fan_in")
            elif ring.pattern_type == "fan_out":
                scores[acc] += settings.SCORE_FAN_OUT
                patterns[acc].add("fan_out")
            elif ring.pattern_type == "shell":
                scores[acc] += settings.SCORE_SHELL
                patterns[acc].add("shell_chain")
            account_rings[acc].append(ring.ring_id)

    # High velocity only boosts already suspicious accounts (multi-signal)
    for acc in list(scores.keys()):
        if acc in high_velocity_accounts:
            scores[acc] += settings.SCORE_HIGH_VELOCITY
            patterns[acc].add("high_velocity")

    # Cap scores
    for acc in scores:
        scores[acc] = min(scores[acc], settings.SCORE_MAX)

    return scores, patterns, account_rings


def build_graph_data(
    g: nx.DiGraph,
    scores: Dict[str, float],
    patterns: Dict[str, Set[str]],
    transactions: Iterable[Transaction],
) -> GraphData:
    nodes: List[GraphNode] = []
    for node in g.nodes:
        nodes.append(
            GraphNode(
                id=node,
                label=node,
                suspicion_score=scores.get(node),
                detected_patterns=sorted(patterns.get(node, [])),
            )
        )

    edges: List[GraphEdge] = []
    for u, v, data in g.edges(data=True):
        edges.append(
            GraphEdge(
                id=str(data.get("transaction_id", f"{u}->{v}")),
                source=u,
                target=v,
                amount=float(data.get("amount", 0.0)),
                timestamp=data.get("timestamp"),
            )
        )

    return GraphData(nodes=nodes, edges=edges)


def assemble_analysis_result(
    transactions: List[Transaction],
    processing_time_seconds: float,
) -> Tuple[AnalysisResult, GraphData]:
    g = build_graph(transactions)

    cycle_rings = detect_cycle_rings(g)
    smurf_rings = detect_smurf_rings(transactions)
    shell_rings = detect_shell_rings(g, transactions)

    all_rings: Dict[Tuple[str, ...], FraudRing] = {}
    all_rings.update(cycle_rings)
    for key, ring in smurf_rings.items():
        all_rings.setdefault(key, ring)
    for key, ring in shell_rings.items():
        all_rings.setdefault(key, ring)

    high_velocity_accounts = detect_high_velocity(transactions)

    scores, patterns, account_rings = compute_scores_and_patterns(
        all_rings, high_velocity_accounts
    )

    # Build fraud_rings list
    fraud_rings = list(all_rings.values())

    # Map account to "primary" ring: pick highest risk
    primary_ring_for_account: Dict[str, str] = {}
    risk_by_ring: Dict[str, float] = {r.ring_id: r.risk_score for r in fraud_rings}
    for acc, ring_ids in account_rings.items():
        if not ring_ids:
            continue
        best_ring = max(ring_ids, key=lambda r_id: risk_by_ring.get(r_id, 0.0))
        primary_ring_for_account[acc] = best_ring

    suspicious_accounts = []
    for acc, score in scores.items():
        ring_id = primary_ring_for_account.get(acc)
        if not ring_id:
            # Should not happen because scores are only assigned via rings
            continue
        suspicious_accounts.append(
            {
                "account_id": acc,
                "suspicion_score": score,
                "detected_patterns": sorted(patterns.get(acc, [])),
                "ring_id": ring_id,
            }
        )

    # Sort descending by suspicion_score
    suspicious_accounts.sort(key=lambda x: x["suspicion_score"], reverse=True)

    result = AnalysisResult(
        suspicious_accounts=suspicious_accounts,
        fraud_rings=fraud_rings,
        summary=Summary(
            total_accounts_analyzed=len(g.nodes),
            suspicious_accounts_flagged=len(suspicious_accounts),
            fraud_rings_detected=len(fraud_rings),
            processing_time_seconds=processing_time_seconds,
        ),
    )

    graph_data = build_graph_data(g, scores, patterns, transactions)

    return result, graph_data

