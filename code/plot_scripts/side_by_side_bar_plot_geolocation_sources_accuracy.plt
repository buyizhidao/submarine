set terminal pdfcairo dashed font "Gill Sans,10" linewidth 2 rounded fontscale 1.0

# Line style for axes
set style line 80 lt rgb "#808080"

# Line style for grid
set style line 81 lt 0  # dashed
set style line 81 lt rgb "#808080"  # grey

set grid back linestyle 81
set border 3 back linestyle 80 # Remove border on top and right.  These
             # borders are useless and make it harder
                          # to see plotted lines near the border.
                              # Also, put it in grey; no need for so much emphasis on a border.
                              set xtics nomirror
                              set ytics nomirror


#set key Left inside top left font ",9" 
#set boxwidth 0.75
set style histogram clustered
#set key autotitle columnheader
unset title
#set lmargin 30
set key outside horizontal font ",8"
set offset -0.45,-0.45,0, 0
#set xlabel "Granularity"
set ylabel "Accuracy (%)"
set boxwidth 1
set yrange[0:100]
#set style fill pattern
set output "plot_results/Fig-geolocation-source-accuracies.pdf"

plot 'plot_results/geolocation_accuracies.dat' u 3 with histogram title columnhead(3) lt rgb "#8b008b" fillstyle pattern 1, \
     "" u 4:xtic(2) with histogram title columnhead(4) lc rgb "#00ff7f" fillstyle pattern 2, \
     "" u 5 with histogram title columnhead(5) lc rgb "#ffd700" fillstyle pattern 3, \
     "" u 6 with histogram title columnhead(6) lc rgb "#7f7f7f" fillstyle pattern 4, \
     "" u 7 with histogram title columnhead(7) lc rgb "#000000" fillstyle pattern 5, \
     "" u 8 with histogram title columnhead(8) lc rgb "#ff8c00" fillstyle pattern 6, \
     "" u 9 with histogram title columnhead(9) lc rgb "#9932cc" fillstyle pattern 7, \
     "" u 10 with histogram title columnhead(10) lc rgb "#e9967a" fillstyle pattern 8, \
     "" u 11 with histogram title columnhead(11) lc rgb "#ff1493" fillstyle pattern 9, \
     "" u 12 with histogram title columnhead(12) lc rgb "#006400" fillstyle pattern 10, \
     "" u 13 with histogram title columnhead(13) lc rgb "#00008b" fillstyle pattern 12, \
     "" u 14 with histogram title columnhead(14) lc rgb "#ff0000" fillstyle pattern 11   