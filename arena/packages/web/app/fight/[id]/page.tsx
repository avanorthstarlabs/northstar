"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { ArenaScene } from "../../../components/arena/ArenaScene";
import { useGameState } from "../../../components/arena/useGameState";

export default function FightPage() {
  const params = useParams();
  const fightId = params.id as string;
  const { state, refetch } = useGameState(fightId);

  // Poll for updates every 1 second as fallback
  useEffect(() => {
    const interval = setInterval(refetch, 1000);
    return () => clearInterval(interval);
  }, [refetch]);

  return <ArenaScene gameState={state} />;
}
