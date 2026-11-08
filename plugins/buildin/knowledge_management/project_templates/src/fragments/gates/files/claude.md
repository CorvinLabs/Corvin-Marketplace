## Gates

A decision becomes `implementation_ready` when G1 (it links its concept), G2 (the concept links back), G3 (an epic implements it, shares a `paths:` entry with it, every task has a definition of done) and G4 (a review closed with `kb review close`) hold. `kb check` lists what is missing. A code task is done only with its evidence (`kb task <T> done --evidence call_site=... --evidence e2e_test=... --evidence exit_code=0 --evidence commit=<sha on origin/main>`).
