awk -F"|" 'NR==1{for(i=1;i<=NF;i++)h[i]=$i;next}{k=$2;for(i=1;i<=NF;i++){if(i!=1&&i!=3)s[k,i]+=$i;else if(i==1)id[k]=$i;else if(i==3)nm[k]=$i}}END{out=h[1] FS h[2] FS h[3];for(i=4;i<=length(h);i++)if(i!=3)out=out FS h[i];print out > "Aggregated_PMI.out";for(k in id){l=id[k] FS k FS nm[k];for(i=4;i<=length(h);i++)if(i!=3)l=l FS s[k,i]+0;print l >> "Aggregated_PMI.out"}}' input_file.txt


# version 2 define inuout and output, output in decimal format not scientific
outfile="Aggregated_PMI.out" && awk -v out="$outfile" -F"|" 'NR==1{for(i=1;i<=NF;i++)h[i]=$i;next}{k=$2;for(i=1;i<=NF;i++){if(i!=1&&i!=3)s[k,i]+=$i;else if(i==1)id[k]=$i;else if(i==3)nm[k]=$i}}END{l=h[1] FS h[2] FS h[3];for(i=4;i<=length(h);i++)if(i!=3)l=l FS h[i];print l > out;for(k in id){l=id[k] FS k FS nm[k];for(i=4;i<=length(h);i++)if(i!=3)l=l FS sprintf("%.10f",s[k,i]+0);print l >> out}}' input_file.txt
