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
#set title "Test"
#set key invert reverse Left outside
set key Left inside top right font ",9" # top outside
set key autotitle columnheader
set auto y
set auto x
unset xtics
set xtics  scale 0
set style data histogram
set style histogram rowstacked
#set style fill solid border -1
#set style fill pattern

set ylabel "# of links (in millions)" font ",10" 
set xlabel '# cables predicted' font ",10"

set boxwidth 0.5
set offset -0.25,-0.25,0, 0
set datafile separator " "
#set terminal pdfcairo dashed font "Gill Sans,10" linewidth 2 #rounded fontscale 1.0
set output "plot_results/Fig-count_all_v4.pdf"
plot \
  'plot_results/all_count_sol_validated_541_v4.dat' \
  using (column(2)/1e6):xticlabels(1) t "S, B" fillstyle pattern 1 , \
 '' using (column(3)/1e6):xticlabels(1) t "S, O" fillstyle pattern 2, \
 '' using (column(4)/1e6):xticlabels(1) t "S, N" fillstyle pattern 3, \
  '' using (column(5)/1e6):xticlabels(1) t "U, B" fillstyle pattern 4, \
  '' using (column(6)/1e6):xticlabels(1) t "U, O" fillstyle pattern 7 lc rgb 'red', \
  '' using (column(7)/1e6):xticlabels(1) t "U, N" fillstyle pattern 6
