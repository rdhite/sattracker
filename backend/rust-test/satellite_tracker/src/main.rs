use clap::{Parser, Subcommand};
use std::path::PathBuf;
use chrono::{Utc, Duration};
use anyhow::Result;

mod coords;
mod tle;
mod predict;

use coords::Observer;

#[derive(Parser)]
#[command(name = "satellite_tracker")]
#[command(about = "Track satellites using TLE data", long_about = None)]
struct Cli {
    /// Path to TLE file
    #[arg(short, long, value_name = "FILE")]
    tle: PathBuf,

    /// Observer Latitude (degrees)
    #[arg(long)]
    lat: f64,

    /// Observer Longitude (degrees)
    #[arg(long)]
    lon: f64,

    /// Observer Altitude (meters)
    #[arg(long, default_value_t = 0.0)]
    alt: f64,
    
    /// Minimum elevation angle for visibility (degrees)
    #[arg(long, default_value_t = 0.0)]
    min_el: f64,

    #[command(subcommand)]
    command: Commands,
}

#[derive(Subcommand)]
enum Commands {
    /// Check current visibility of all satellites in TLE
    Now,
    /// Predict passes for the next X hours
    Predict {
        /// Hours to predict ahead
        #[arg(long, default_value_t = 24.0)]
        hours: f64,
    },
}

fn main() -> Result<()> {
    let cli = Cli::parse();
    
    let observer = Observer::new(cli.lat, cli.lon, cli.alt);
    let satellites = tle::parse_tle_file(&cli.tle)?;
    
    println!("Loaded {} satellites.", satellites.len());
    println!("Observer: Lat {}, Lon {}, Alt {}m", cli.lat, cli.lon, cli.alt);
    
    match cli.command {
        Commands::Now => {
            let now = Utc::now();
            println!("\nCurrent Positions ({}):", now);
            println!("{:<20} | {:<10} | {:<10} | {:<10} | {:<10}", "Name", "Azimuth", "Elevation", "Range (km)", "Visible");
            println!("{:-<75}", "");
            
            for sat in satellites {
                match predict::predict_position(&sat.elements, &observer, now) {
                    Ok(pos) => {
                         let visible = if pos.elevation >= cli.min_el { "YES" } else { "NO" };
                         
                         println!("{:<20} | {:10.2} | {:10.2} | {:10.2} | {}", sat.name, pos.azimuth, pos.elevation, pos.range, visible);
                    },
                    Err(e) => eprintln!("Error propagating {}: {}", sat.name, e),
                }
            }
        }
        Commands::Predict { hours } => {
            let now = Utc::now();
            let duration = Duration::minutes((hours * 60.0) as i64);
            
            println!("\nPasses for next {} hours (Min El: {} deg):", hours, cli.min_el);
            
            for sat in satellites {
                 match predict::find_passes(&sat.elements, &observer, now, duration, cli.min_el) {
                     Ok(passes) => {
                         if !passes.is_empty() {
                             println!("\nSatellite ({}):", sat.name);
                             for pass in passes {
                                 println!("  AOS: {} | LOS: {} | Max El: {:.2}", pass.aos, pass.los, pass.max_elevation);
                             }
                         }
                     },
                     Err(e) => eprintln!("Error predicting passes for {}: {}", sat.name, e),
                 }
            }
        }
    }

    Ok(())
}
