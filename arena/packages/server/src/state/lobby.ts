import { nanoid } from "nanoid";
import { Fight } from "../combat/fight.js";
import type { Action } from "../combat/actions.js";

export interface Agent {
  id: string;
  skillsMd: string;
  walletAddress: string;
  characterId: string;
  wins: number;
  losses: number;
  registeredAt: number;
}

export interface Challenge {
  id: string;
  challengerId: string;
  targetId: string;
  wagerAmount: number;
  createdAt: number;
  status: "pending" | "accepted" | "declined" | "expired";
}

export class Lobby {
  agents = new Map<string, Agent>();
  challenges = new Map<string, Challenge>();
  fights = new Map<string, Fight>();
  fightAgents = new Map<string, [string, string]>();

  registerAgent(id: string, skillsMd: string, walletAddress: string, characterId: string): Agent {
    if (this.agents.has(id)) throw new Error(`Agent ${id} already registered`);
    const agent: Agent = { id, skillsMd, walletAddress, characterId, wins: 0, losses: 0, registeredAt: Date.now() };
    this.agents.set(id, agent);
    return agent;
  }

  createChallenge(challengerId: string, targetId: string, wagerAmount: number): Challenge {
    if (!this.agents.has(challengerId)) throw new Error("Challenger not registered");
    if (!this.agents.has(targetId)) throw new Error("Target not registered");
    if (challengerId === targetId) throw new Error("Cannot challenge yourself");
    const challenge: Challenge = {
      id: nanoid(),
      challengerId,
      targetId,
      wagerAmount,
      createdAt: Date.now(),
      status: "pending",
    };
    this.challenges.set(challenge.id, challenge);
    return challenge;
  }

  acceptChallenge(challengeId: string, agentId: string): Fight {
    const challenge = this.challenges.get(challengeId);
    if (!challenge) throw new Error("Challenge not found");
    if (challenge.targetId !== agentId) throw new Error("Not the challenge target");
    if (challenge.status !== "pending") throw new Error("Challenge not pending");

    challenge.status = "accepted";
    const fightId = nanoid();
    const fight = new Fight(fightId, challenge.challengerId, challenge.targetId);
    this.fights.set(fightId, fight);
    this.fightAgents.set(fightId, [challenge.challengerId, challenge.targetId]);
    return fight;
  }

  submitAction(fightId: string, agentId: string, action: Action) {
    const fight = this.fights.get(fightId);
    if (!fight) throw new Error("Fight not found");
    return fight.submitAction(agentId, action);
  }

  getFight(fightId: string): Fight | undefined {
    return this.fights.get(fightId);
  }

  getActiveFights(): Array<{ fightId: string; agents: [string, string] }> {
    const active: Array<{ fightId: string; agents: [string, string] }> = [];
    for (const [fightId, fight] of this.fights) {
      if (fight.getState().status !== "fight_over") {
        active.push({ fightId, agents: this.fightAgents.get(fightId)! });
      }
    }
    return active;
  }
}
