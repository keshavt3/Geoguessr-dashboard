//Fetch all recent team duel tokens:
await (async (userId) => {
  let token = "";
  let results = [];
  let page = 1;

  function extractIdsFromPayload(rawPayload) {
    let out = [];
    let parsed;

    try {
        parsed = JSON.parse(rawPayload);
    } catch {
        return out;
    }

    const items = Array.isArray(parsed) ? parsed : [parsed];

    for (const item of items) {
        // Check top level first
        let gameMode = item.gameMode;
        let gameId = item.gameId;

        // If not found, check payload
        if ((!gameMode || !gameId) && item.payload) {
            gameMode = item.payload.gameMode;
            gameId = item.payload.gameId;
        }

        if (gameMode === "TeamDuels" && gameId) {
            out.push(gameId);
        }
    }

    return out;
}


  while (true) {
    let url = "https://www.geoguessr.com/api/v4/feed/private";
    if (token) url += "?paginationToken=" + token;

    console.log("Fetching page", page++);

    const res = await fetch(url);
    const data = await res.json();

    if (!data.entries || data.entries.length === 0) {
      console.log("No more entries — stopping.");
      break;
    }

    for (const entry of data.entries) {
      if (typeof entry.payload === "string") {
        results.push(...extractIdsFromPayload(entry.payload));
      }
    }

    if (!data.paginationToken) {
      console.log("No pagination token — stopping.");
      break;
    }

    token = data.paginationToken;

    await new Promise(r => setTimeout(r, 300)); // be nice to the server
  }

  results = [...new Set(results)];
  return results;
})("60314c8c098571000133cd25"); //change this to whatever your personal token is.



//Return most recent team duel summary link: 
await (async (userId) => {
  let token = "";
  let page = 1;

  function extractMostRecentTeamDuelId(rawPayload) {
    let parsed;
    try {
        parsed = JSON.parse(rawPayload);
    } catch {
        return null;
    }

    const items = Array.isArray(parsed) ? parsed : [parsed];

    for (const item of items) {
        // Top level first
        let gameMode = item.gameMode;
        let gameId = item.gameId;

        // If not found, check payload
        if ((!gameMode || !gameId) && item.payload) {
            gameMode = item.payload.gameMode;
            gameId = item.payload.gameId;
        }

        if (gameMode === "TeamDuels" && gameId) {
            return gameId; // return immediately on first match
        }
    }

    return null;
  }

  while (true) {
    let url = "https://www.geoguessr.com/api/v4/feed/private";
    if (token) url += "?paginationToken=" + token;

    console.log("Fetching page", page++);

    const res = await fetch(url);
    const data = await res.json();

    if (!data.entries || data.entries.length === 0) {
      console.log("No more entries — stopping.");
      break;
    }

    for (const entry of data.entries) {
      if (typeof entry.payload === "string") {
        const recentId = extractMostRecentTeamDuelId(entry.payload);
        if (recentId) {
          console.log(`https://www.geoguessr.com/team-duels/${recentId}/summary`);
          return recentId; // stop everything once we find it
        }
      }
    }

    if (!data.paginationToken) {
      console.log("No pagination token — stopping.");
      break;
    }

    token = data.paginationToken;
    await new Promise(r => setTimeout(r, 300));
  }

  console.log("No TeamDuels entries found.");
  return null;
})("60314c8c098571000133cd25"); //change for whoever needs to use it

//return stats given a list of tokens
async function fetchTeamDuels(ids, myId, teammateId = null, competitiveOnly = false) {
    const results = [];

    for (let gameToken of ids) {
        console.log(`Fetching duel ${gameToken}...`);

        let res = await fetch(`https://game-server.geoguessr.com/api/duels/${gameToken}`);
        let game = await res.json();

        // Filter non-competitive games
        if (competitiveOnly && !game.teams.some(t => t.players.some(p => p.progressChange?.competitiveProgress))) {
            continue;
        }

        // Find MY team
        let myTeam = game.teams.find(t => t.players.some(p => p.playerId === myId));
        if (!myTeam) continue;

        // Filter by teammate if provided
        if (teammateId && !myTeam.players.some(p => p.playerId === teammateId)) {
            continue;
        }

        // --- Statistics structures ---
        let teamStats = {
            totalDistance: 0,
            totalScore: 0,
            totalRounds: 0,
            totalHealthChange: 0
        };

        let playerStats = {};
        let roundsMap = {};  // roundNumber → aggregate stats

        // 1. PROCESS PLAYER GUESSES (distance, score, time, country)
        for (let player of myTeam.players) {
            let pStats = { distance: 0, score: 0, rounds: [] };

            for (let guess of player.guesses) {
                let round = game.rounds[guess.roundNumber - 1];
                let roundTime = (new Date(guess.created) - new Date(round.startTime)) / 1000;

                pStats.distance += guess.distance;
                pStats.score += guess.score;

                pStats.rounds.push({
                    roundNumber: guess.roundNumber,
                    distance: guess.distance,
                    score: guess.score,
                    time: roundTime,
                    country: round.panorama?.countryCode
                });

                // Initialize round bucket if missing
                if (!roundsMap[guess.roundNumber]) {
                    roundsMap[guess.roundNumber] = {
                        roundNumber: guess.roundNumber,
                        totalDistance: 0,
                        totalScore: 0,
                        totalHealthChange: 0,
                        countries: new Set()
                    };
                }

                // Aggregate into round
                roundsMap[guess.roundNumber].totalDistance += guess.distance;
                roundsMap[guess.roundNumber].totalScore += guess.score;

                if (round.panorama?.countryCode) {
                    roundsMap[guess.roundNumber].countries.add(round.panorama.countryCode);
                }
            }

            // Add player's totals to team
            teamStats.totalDistance += pStats.distance;
            teamStats.totalScore += pStats.score;
            teamStats.totalRounds += player.guesses.length;

            playerStats[player.playerId] = pStats;
        }

        // 2. PROCESS HEALTH CHANGES FROM *YOUR TEAM'S* roundResults
        for (let rr of myTeam.roundResults || []) {
            if (rr.healthBefore != null && rr.healthAfter != null) {
                let delta = rr.healthAfter - rr.healthBefore;

                teamStats.totalHealthChange += delta;

                if (!roundsMap[rr.roundNumber]) {
                    roundsMap[rr.roundNumber] = {
                        roundNumber: rr.roundNumber,
                        totalDistance: 0,
                        totalScore: 0,
                        totalHealthChange: 0,
                        countries: new Set()
                    };
                }

                roundsMap[rr.roundNumber].totalHealthChange = delta;
            }
        }

        // 3. FINALIZE ROUND STAT ARRAY
        let roundStats = Object.values(roundsMap).map(r => ({
            roundNumber: r.roundNumber,
            totalDistance: r.totalDistance,
            totalScore: r.totalScore,
            totalHealthChange: r.totalHealthChange,
            countries: Array.from(r.countries)
        }));

        // ---------------------------------------------------------
        // 4. FINAL RESULT
        // ---------------------------------------------------------
        results.push({
            gameId: game.gameId,
            teamId: myTeam.id,
            teamStats,
            playerStats,
            roundStats
        });

        // Avoid rate limit
        await new Promise(r => setTimeout(r, 100));
    }

    return results;
}
// Usage example:
//const ids = /*---> DATA FROM LAST STEP HERE <---*/;
//const my_id = "---> YOUR ID HERE <---";
//let data = await fetchTeamDuels(ids, my_id);
//console.log(JSON.stringify(data, null, 2));