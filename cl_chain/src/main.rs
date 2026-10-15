//! Znajduje łańcuch CL (related changes) w mirrorze repo Gerrita.
//!
//! Użycie (w katalogu mirrora z pobranymi refs/changes/*):
//!     cl_chain <numer_zmiany>
//!
//! Algorytm:
//! 1. Spisz wszystkie refs/changes/XX/N/PS: sha -> (zmiana, ps) oraz zmiana -> bieżący ps.
//! 2. Dla bieżącego patch setu każdej zmiany sprawdź rodzica. Jeśli rodzic jest
//!    patch setem innej zmiany (dowolnym, także starym), to krawędź dziecko -> rodzic.
//!    Rodzic na starym patch secie = zmiana nieaktualna (wymaga rebase).
//! 3. BFS od zadanej zmiany w obie strony (rodzice + dzieci) = cały łańcuch.

use git2::{Oid, Repository};
use std::collections::{HashMap, HashSet, VecDeque};

// refs/changes/34/1234/3 -> (1234, 3); /meta, /robot-comments itd. -> None
fn parse(r: &str) -> Option<(u32, u32)> {
    let mut it = r.strip_prefix("refs/changes/")?.split('/');
    it.next()?; // shard
    let ch = it.next()?.parse().ok()?;
    let ps = it.next()?.parse().ok()?;
    it.next().is_none().then_some((ch, ps))
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let start: u32 = std::env::args()
        .nth(1)
        .ok_or("użycie: cl_chain <numer_zmiany>")?
        .parse()?;
    let repo = Repository::discover(".")?;

    // 1. oid -> (zmiana, ps), zmiana -> bieżący ps
    let mut ps_of: HashMap<Oid, (u32, u32)> = HashMap::new();
    let mut cur: HashMap<u32, (u32, Oid)> = HashMap::new();
    // glob w libgit2: '*' łapie też '/', więc to obejmuje wszystkie poziomy
    for r in repo.references_glob("refs/changes/*")? {
        let r = r?;
        let (Ok(name), Some(oid)) = (r.name(), r.target()) else { continue };
        let Some((ch, ps)) = parse(name) else { continue };
        ps_of.insert(oid, (ch, ps));
        let e = cur.entry(ch).or_insert((0, oid));
        if ps > e.0 {
            *e = (ps, oid);
        }
    }
    if !cur.contains_key(&start) {
        return Err(format!("brak zmiany {start} w refs/changes").into());
    }

    // 2. rodzice bieżących patch setów -> krawędzie
    let mut up: HashMap<u32, HashSet<u32>> = HashMap::new();
    let mut down: HashMap<u32, HashSet<u32>> = HashMap::new();
    let mut stale: HashSet<u32> = HashSet::new();
    for (&ch, &(_, oid)) in &cur {
        let Ok(commit) = repo.find_commit(oid) else { continue }; // brakujący obiekt: pomiń
        for p in commit.parent_ids() {
            let Some(&(pch, pps)) = ps_of.get(&p) else { continue };
            if pch == ch {
                continue;
            }
            up.entry(ch).or_default().insert(pch);
            down.entry(pch).or_default().insert(ch);
            if pps != cur[&pch].0 {
                stale.insert(ch); // stoi na starym PS rodzica
            }
        }
    }

    // 3. BFS w obie strony
    let empty = HashSet::new();
    let mut seen = HashSet::from([start]);
    let mut q = VecDeque::from([start]);
    while let Some(c) = q.pop_front() {
        let ns = up.get(&c).unwrap_or(&empty).iter().chain(down.get(&c).unwrap_or(&empty));
        for &n in ns {
            if seen.insert(n) {
                q.push_back(n);
            }
        }
    }

    let sorted = |m: &HashMap<u32, HashSet<u32>>, c: u32| {
        let mut v: Vec<u32> = m.get(&c).map(|s| s.iter().copied().collect()).unwrap_or_default();
        v.sort_unstable();
        v
    };
    let mut chain: Vec<u32> = seen.into_iter().collect();
    chain.sort_unstable();
    for c in chain {
        println!(
            "{c} rodzic: {:?} dzieci: {:?}{}",
            sorted(&up, c),
            sorted(&down, c),
            if stale.contains(&c) { " NIEAKTUALNY (rebase)" } else { "" }
        );
    }
    Ok(())
}
