# Note you need gnuplot 4.4 for the pdfcairo terminal.
#set terminal pdfcairo font "Helvetica,8" linewidth 4 rounded
#set size ratio 0.6
#set terminal postscript monochrome font "Helvetica, 22" linewidth 4 rounded 
set terminal pdfcairo dashed font "Gill Sans,10" linewidth 2 rounded fontscale 1.0

# Line style for axes
set style line 80 lt rgb "#808080"

# Line style for grid
set style line 81 lt 0  # dashed
set style line 81 lt rgb "#808080"  # grey
# set missing "?"

set grid back linestyle 81
set border 3 back linestyle 80 # Remove border on top and right.  These
             # borders are useless and make it harder
                          # to see plotted lines near the border.
                              # Also, put it in grey; no need for so much emphasis on a border.
                              set xtics nomirror
                              set ytics nomirror

set output "plot_results/Fig-scores-541_all_v4.pdf"
set ylabel "CDF" font ",10" 
set xlabel "Score" font ",10" #offset 2

#unset key
set key Left inside top left font ",9" # top outside
set key samplen 1.1
#set key title "Over-allocation factor"
#set key inside top right font ",9" 
#set key above font ",7" horizontal
#set key spacing 0.5 samplen 0.5 height 0.7

set xtics font ",10"
set ytics font ",10" #0,.1,0.5
set style line 1 lt 1 lw 0.5
#set xrange [90:0]
#set logscale x
#set yrange[0:]
set xrange[0:1]
#set yrange[0:100]

plot \
  "plot_results/bg_oc_sol_validated_541_v4-cdf.txt" using 1:3 title "S, B"  with lines lc rgb "#332288" lw 2 lt 2 dashtype 8, \
  "plot_results/og_oc_sol_validated_541_v4-cdf.txt" using 1:3 title "S, O"  with lines lc rgb "#88CCEE" lw 2 lt 2 dashtype 2 , \
  "plot_results/bb_oc_sol_validated_541_v4-cdf.txt" using 1:3 title "S, N"  with lines lc rgb "#44AA99" lw 2 lt 2 dashtype 3, \
  "plot_results/bg_te_sol_validated_541_v4-cdf.txt" using 1:3 title "U, B"  with lines lc rgb "#999933" lw 2 lt 2 dashtype 4, \
  "plot_results/og_te_sol_validated_541_v4-cdf.txt" using 1:3 title "U, O"  with lines lc rgb "#CC6677" lw 2 lt 2 dashtype 5 , \
  "plot_results/bb_te_sol_validated_541_v4-cdf.txt" using 1:3 title "U, N"  with lines lc rgb "#AA4499" lw 2 lt 2 dashtype 7 , \
  "plot_results/all_scores_sol_validated_541_v4-cdf.txt" using 1:3 title "All" with lines lc rgb "black" lw 2 lt 2 dashtype 1

