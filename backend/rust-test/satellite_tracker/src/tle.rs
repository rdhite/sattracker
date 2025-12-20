use sgp4::Elements;
use anyhow::{Context, Result};
use std::fs::File;
use std::io::{BufRead, BufReader};
use std::path::Path;

pub struct Tle {
    pub name: String,
    pub elements: Elements,
}

pub fn parse_tle_file<P: AsRef<Path>>(path: P) -> Result<Vec<Tle>> {
    let file = File::open(path.as_ref()).context("Failed to open TLE file")?;
    let all_lines: Vec<String> = BufReader::new(file)
        .lines()
        .collect::<Result<_, _>>()?;
        
    let mut tle_list = Vec::new();
    let mut i = 0;
    
    while i < all_lines.len() {
        let line = all_lines[i].trim();
        if line.starts_with("1 ") {
            if i + 1 < all_lines.len() {
                let line2 = all_lines[i+1].trim();
                if line2.starts_with("2 ") {
                    let name = if i > 0 {
                        let prev = all_lines[i-1].trim();
                        // Assume non-TLE-data line is a name
                        if !prev.starts_with("1 ") && !prev.starts_with("2 ") && !prev.is_empty() {
                            Some(prev.to_string())
                        } else {
                            None
                        }
                    } else {
                        None
                    };
                    
                    let name_str = name.clone().unwrap_or_else(|| format!("SAT-{}", i));

                    // Parse
                    match Elements::from_tle(name, line.as_bytes(), line2.as_bytes()) {
                        Ok(elem) => tle_list.push(Tle { name: name_str, elements: elem }),
                        Err(e) => eprintln!("Failed to parse TLE for {:?}: {}", name_str, e),
                    }
                    
                    i += 2;
                    continue;
                }
            }
        }
        i += 1;
    }
    
    Ok(tle_list)
}
