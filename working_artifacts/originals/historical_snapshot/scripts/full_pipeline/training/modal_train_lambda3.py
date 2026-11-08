import modal

app = modal.App("splade-lambda-screen")
volume = modal.Volume.from_name("splade-data")

# Match the Kaggle environment versions that were recorded in your corrected runs.
image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install(
        "torch==2.10.0",
        "transformers==5.0.0",
        "pandas",
        "numpy",
        "safetensors",
        "sentencepiece",
    )
    .run_commands(
        "python -c \"from transformers import AutoTokenizer, AutoModelForMaskedLM; "
        "m='naver/splade-cocondenser-ensembledistil'; "
        "AutoTokenizer.from_pretrained(m); AutoModelForMaskedLM.from_pretrained(m)\""
    )
)

EXPECTED_SHA256 = "1610dfd0be9855592deb6717b5feb972f9d95ba402664f0951d50da40032b121"
PAYLOAD = """c-rNCYjfL3lHhm#3JfOt8gP@asJ45ixy{}6wB-rM*dDL#?!7yifq=-Ogb@gE08qACqy6ohk9uSQAVquj%f&eyHi4?j%F4>hS5+l`|GUS#rha^pmycC>6KrqWtE&8d6o%o4I?Kx-D_4QK$%<Xps^I<GSI?fGP2QgcRT;EbD#(gjWvkoC68>w|D!8cHw%SalPrsS0^P*KXyjx{$mW)P!$u2Jo73`YqQUy^}svs{{YOCO%vJJ|rRTout{kTz0lLPdvs)I(URXiJw0{HVg#w>VzO>iE6s_N^!ynNhji)^J*?s)n%-Rz1s$A-!FHkeHCS1|n^ey!@;Nxduo2Y`)6FY+=g2)$+oFUG;?bR0Z69S1-BVH`|PPLd$_0Mx;e2LLl~gS>&^wlGo{TUHde!8-p8z_ND4<plc4>AwJBp|C~L142O!<gYd*&?H!1W#y%6f(zAtQmPDKEDewq`)QVSzHI~bd8?LfLle_v8x?4h=jC<>uXhbj&~3njv|U6`;w0bRmKQT1&7;7My(l)1O{KJj4hq#a$+EfWS8Hxd=(Ek2={C#jCN)!UYa>SMYF7tUonI2|@}}9T;OF<hHnu{0RVxL9fTmdEQM$?6<rVafU<?l;Yam%0KxQ<035=s|fK!%0(*}4oc=hTvu`Iu?6*DH&gwcYzfo4#euX8HMS}YwAl?+1%%c^W)>`m~8@sCfQ03dt<`u%+e4OK&Z{BSycI(-@#+KjQgs%+YN2eU8&jPxj57*i8OdATfhD<t_<R<9<dx`g4}D6Z7RW1JuWOkLbgR(bQc3Rs32Wdx(oS3G=Tm@#3{WH;F4^0G!?D%cjg23O96U`U!(yB3)s!G%2<t?OzNr0IIs?rN2$LB82mH4MIlWk~gbw&q=Zxy|ZEndhslxhnDt^Z2)>D$Q@0uPgJrYRoTYVf$nOHCMYfFYME;ZP4Z$#Tae@AoOL>dyDX?puOE99rgR?`4Z^y66Q9$DAYK3l{fJGI@@BUaqwONHOi&JU-16J4ra>^uiR~5X=hDPZq2JLAPg_y?{;Nzs_NyH_mGq&H7mPsll87#@-oK?FEqwfiX(0k5(@@*`2DJa^;nPTH}JJ?0Ca2CRlQMlV=6}^yq@ja>UFhJ#fz$boi*2L_3HK5mVBtLRhj<=@aWa0YSRKZH>=ZTd8JmnLZzSb_A339)tlXRJc>u7(b@lgd-n5(v*+o%vk%W+zJVYA@ypq}muK&TdGLo6_+Qp|{nuZ;3e)t-$x~P1!@HMnU!8rxk{?b}SRbR;e|>)TDt+_p^%=YiOJLbr3);!Df&~NezX6uTe>X6H!1zEVVA9b_tpnn{6qvAy;$ZTxmK~EfAmEy9wp243C%vqp16$!)eYx9!z<o<4Q7oz@*=mI_sXPi<u!m!0D>a8Thb#H-yBs9g{6oD1#<^0(cFqbB`Hrd|28e644;Dt0fl8S_IX&2#MA4+Ks@Akd)_2YEDGH79qS|465F#)Cqd{tY_yAC~t(I5K-~hir*zf`c`=kLb9c+A<IG1&{nq<r6ZZp_;`oqE2u-+#)I#^X-(YLlCpk+o&d>%HiuobAs9S()r<X0BeTK%Iwe}Gr6^X&vh^)Og&3kqmgmj;Af6?&ndAWl~x&7$h!Z?gdYQ79Ergw9BE((-u&c9&T&?G?fSB$CbbDz77cXf(^K&#(^D>Y5%I2b3G!t^%_y3O@nDAXqEZY4dQ`t|xyCW0ZMdsjLd!5B@>i5`)`V7mvyQD}m$)r9nlMHOoAozsQP4nPD|o+3C|CA~%dN7(%=9Iz{f8p-qJ%DER58;Piw>2<n$RUgcmdVX4+wi3T-1mil5Cb&$Z^A#@ewpkksT+gz-&nXZ|jxez&&K#gC7Ve9}nRFd5m*@7#3v#QIl)Mx%>C$$9mpXRFw^|&&V>JKvq8M#XGrp&mO=vqSug|92-4Old72D*^zj?pLqCMmZG8mE`4j{D7_C#<ER#|L1oiz;Ji^b5Emj>$}+M-2c_O?79{ah;+01k;E`8bpI8S7cGC73f^BLs6<kbvXIAkE`!KCMUSQp=rMpe0x5doGwP4mzwI!LS-eW%dE)iL!`I#?N36WfQN@r<{nV5XKhNBU)1Jpq1=kSs8+Y`smLw>)NudQFxBMokfsu*4}u%4g9TiL`xvamMIN)R!#mgU{m1fSd1w2e$5$HVI|27T>{0+0zw@(D{E!+;Q9}uNg+F+(OJF1ts{k1dymKsC0KVrujkr*?C7$BCruAw;CiP`eT}0uaLnD_f3qb%YVQD#OE5USYX&F2Y!b9Fq7$+o1o2Vla+;9@GQ^5(=0OOJ2YB0s+pdAxu;E@I|@<P3-+85QXT%FZ*RYxB9@J$6$1^f}vBewz60o%y47o39wlW-Lb(j^FenB;LB8mz6ZNAdgMZLQYOHH8Z5HeZ8&LpQa^m%u`|K?z3O%JU^jUO;sYFPNynw~dAewmTZjtKeHe^ac?9)_8;9*8L2`07nbxXxzIMSkBNx4itpmvNfOzcJC_ba8%NOb?pdvt#0Qm<%8`k@Cmz35a-}`V983f!?8~)ja^8yn6q5l#z|3qLb2ypE<pcqxhUWzr|pIsMPm3T6I+pNq0IwQQ|2vpIK(*`P5^?@7JEJX(x7!~V>ph3X0l0hezNc+f>$EfxB3k8jVz*is~hAT%o@^ihQ#SCb`s^_*~01;D-*mwsh0Pz@<+V%<a(uLjNO?z2<CH(f_X;`7IFb<L>^v!>+m&5b0puLfqJjk-JL`5UL&Q!GT(LBE%f6vH`CL7TqHRs_GU!Gchk|R0%kHrK^?8uGt^e-ZN8`hPoh1%cu$cHYgL4-2(U?rov+r(vMP3)l7k=NKtWH_uGZ%g%p&=81;Qfgy@v6D>Vy$t3BQXU#^b^6EQn(pi)O~)Hgt*3!*CHiBATz(F<Y;n=Kzp?7`=w#DK$|pR`BU2+YW0t3|ySU1defL7mQI;?dm15{+-1zZ1PJ07tVt4J^h+ID_3=uuTo$-V3Z<#he0didM83aUSH=_4I4g#hvS-E|A_UkCqEvpc2R>Tk2UEB5491M?zJW}B$#!EizB?Z!V8q36A8rYOos$)?v1BCY1z*Y2p9*)Nq{vnI<$i6M1wsAG|8uMHNY{vP<0C2fl&&^n%|Lm*L_nmNV_D+-V1fH6g&d1Ud3KR-zs3~@)vb$gvuKQehSDC**kg#8Y~7?VJ!mCI~)y)7YmP!G~^@d?>wYuU|}2#|K2l-L6)a_u_G6(l$@YT$-<T7=r!5c5)2<0J=by=du<oCswxoh*MS@W)~G#A4$#4@e(u=_0I8gKe#SftY}9LG9x?t6EMdmTvByGJZpNCp#`y18j!cz&g@X$3VBOqL?u?(v(Bk`Wpam?!bJG?VU*8Au&=lig>tG$eV$<u+(P1{e*Wqg#G+{GiUL<8}8B$AAi;0$&I;stxKY9bZyjZ2y5~Uv4`05!C+Ou)qgLzM4l_I?7QpJq}|4GM&Ss1Zvwb1g{^C9M5Cur;sI}kdef(G%Pb`RUlwc1oSYPAo5DF%_ZfsRGLOEP=+wd0Obu9RRTCLGCuHXW%b#~-_K^<<|RtDRsDm>RmIMx=OpjJ74xTHWO86R@FFC)=vYaXTb6JSq##UP-s`-tQZ+8t!<o%S%<N8n-PqMzU-O3x3D4v-g@z2Z@!oAomd_!DbiWxI~VVxFqgcn?fIa;JSge#K70N>jFsHs>m^lWX#PjDw0kP51P|ska(eacY-Z^R6H0S9?ngvNCfVqi|f}6>l}rn^T_!*L8D5GJ;A2uVy3Z8|K;9>cE&|J_s(x-WE$-Wre;rYu)A_s=1@UKt2)iVm)yGn)18H9O`~cI5fAwM>+p;=fKf#62M7||Ze}u`plB|EJHigIyDp;8Gzs3R^^V+}w&I|HISKHouHdb4@{_RR$-=-<ZJ0TXy-}Mzqknp|77&cmZOh{5?!4Y<D4poW*N&_!m_bi{LSDd7yPI<-+Xn(dzYjiK<&BGw;P0T>;12TNcc3C$-YDMke2r-_mkO-oCaZHiE^ws;tYw9Gv<ghKHmGdpX14X&1dN!n>cH-B=ekDao|ghrUw4q}hv*eeg}ahP&SwgK9Do1h$6%s&%jdy#{N&_mB3!It8sVf!wIb;hdxj(q`6T#h52T;GCFJc;4jI^o_=<V!Wl5%q>26}WGjkB|_QTyEI>=o<b7_e|a#srnCaRGc$z@&bwimaNkR9=PUqd;00*>6a%*<wq3Cfo&#{Et}c72XwT5{6|mRR^Kum}Vo@)}$XbP5JW7g%&AnhJEX!P$7!5L&^gR^aP7!lJ#~myKg1F9(K+;#NkYV-pZ_fki<4M$rl-H!v_3#Dq^>uzicW5Pb3__d|+fiZYHYqZdP`GJ==S!Lp_8_&q0B(DyV;sw!3*-ckX)YLmApo?2Yn4IT|yf#a*Td~yTYl^6mos-}hIGktPmB~~J%@}5I#ot`1j%G15<$~hTyoEHw<>mcE7SBs`}6S23$yyiHF`c7$s1HfE@x@g-v0vKa~d`zO>jfEX$;UZh-#5gekATf$J?s+Qya<*03f!R|?ZcX3GW7NmpsCB6nNJ49BvXkq~wDSQ|brA>u=v3;PtU9E%;W%M>p<rA{xL$t~0%Zv!L$n~7EMI0|wc+_7WKVn8&fvy#IAgu%cZu51tl55~3Z?RcF)SB!w%#bPjo-~oif>u14|#TkyV`H%inVd6V?4qf-rj1vOS}K<e`p)ednd$Fuff6EB&nR}^SU#WAps094}s`Rx2|otNJ1FktS$tP(KcCgZCjfmjh)AZzg<5I-o}iRth|jfFjeMLt6n5TDi^}wB3qeGlA>Ckds8YK`U|m7(ea=!IOGE^9H>Qdh5PWQC-E1VkaxJIyiql~4X8?KKL&UlsQ`(wye55@1ZP^=&v5HATiy5ey|l5*F_N#bbgiE!P88xPK0X7wA~{XE-FNU%Z1gxib{?Mf@;o&h#}69?_OvJ;EChw7gPEuotv}&*j>t1a-Do{OX-dup129e%!Ei)SW58gh(;KpiKE!eCfs`Ib&^H}YLD3g+ZDX_X*4VFRL(z@VnCoT_&PeE>cUqJT#hx=Y(2Nar+sgCfe5>|A^R23vpct_E^yDOXwAVBa9tY9>qkrG+Z5Pjy)Aju~Jp^_Qp1-sU2NCc?g^&AgnBk8N(1*@Td0`tF%nE6vFp{steragJ2z<&1EAw$5FP<giO%%cE))sNCv5X%1lNZv#qp17ZZ^Dj&Yq5`-1C6XVp}h_ADgeZwx6!A8!B52PMJ12#p{Dojht>GJhYp}3WyW@%bO3jgU8|H%D5orO=-^}IRG7cj$l$3?iiaZ!Pku@M76yGu(#`nH5OBjuGCesut}CB(Jl6<9T;k<6$?7`0jd0&pt@^SuF~J(#iloDV`rHi@1mqt9;Umq-JNoZ^i-)@0n7D3pwOg+Xg*wq<APo|LmFPN=sT&JIuxCCG&~=-RncZ-&hbGlFfW__8&Flm7TW7qQ7UweoeqjT2dJ$S!WJfV|`ZU6mUy<z~UdUmQp6EdMuYU%FcuLUa12+JD5psXU(L^6}@kCqfZ0I*m`wL{gz}#RDbRQZ<bFmv>vG!DP@V}^7;O7-Tq=)~5lrMP2*La7<Tm)(DJso*TKsm>pd2^GM`I=8e%4On+a_7gxEM7Cm!JShs1Q^QCL)SAor+-J&!0{mae1vC6UIUd|sKSoB*EE*1<}mS9@(a2_)444{DES)M?aPIlyJi?OcQf>@>EK%tu0?%iBD9Z1tPqSw)?v22XDx=kb30!5L=)&<a=_PgFWT?z-W+Unn2zPj7<c%>o)kd^a|0N)c=sl<V!CsFSj#{xj-1$Y!m(4p_aC6I9k_6vGGG`kUhY;Io)67#vb;cBLfU+yiU5;lMbYc#0&I0vqQKp)$}(9gP;eWtU%`@J0{i27-Cz3xEXb=(R-?~E5f32DvdEey&_=nwrV;7?HHt{P6r=)BGzEl;^>|1Dit%8bgw5%B$K6b_29*z<?TM|7_8VG1f8KXCk7#bgT=TxCIow<f5*SdAk$3`lqj#8ww3Hp7*ZNYmc&5Wri3F+RFjn#=J|$1a$Ya75^f@(OjD4#3Z_Uv3TRWfc>7dmaIt;3gVCr92ct2+Ugl_QGO^O@aX;r6uCLQn#{=r9j#N6(-ctR_&?K|WrKtTJUt2_w?bkOpng$oO%->VlHzseelyE(w1z3`Gm4o*P2yi&{SEs92TaaD<{s(U=$wM-7Siyr6~w0ODBFQNNgqtaytFb;IZl@nXlEjL4b&=h!DQxl&qjdVOmUcetz3HoAzmpE?nC9F7p%}>NsvYtbT-6e21uGQ@<AZ-Ku9&tO|Whv8(qFUlj7}oKmyP)!zE29!4tjr;$dlwq5F7s9&kI@5;9zCKC@%$bZ+PXkRz88w-9@aPy?JEjOkX_mUyQ|++G?}_tU<HX*5{(bwPPY;Nu2r#%xT6@&L<_NZ7+wqJ&wNrHO#D^8nNQ<{AGKECD>E!{k)<R3A|KQZqP9g2TjfUf$H6y2bo%Jg_ostuL$r^3%El{X>{!Jym8m}7jF}DG6&rUg%pvzg=*XesdRNL5C+3xLjD}+y+JkW?T)S!(F;3ionFlTL_%RAm`-KPfrM9(}+noyyaq9$yIvrdlC|z6g9XJH}MrlivFF3nv$h=vP+mb*3^88uw=eNID$36Ru3gMCtpG;5xsIP2nwz#9SqX73bIWcx9-mcbXUE#f&JmIYlmDO~p1~-AA;8abXG9#({@~TZ&YMI@VFL*NL_jGv?tLK&W5%r-KbNf*XS9=?>Csp08M4_FQRZ*Zfr)7<~IeI>%l%%;%s%UJ3?;tyze#O17M+8tDsUoh`xJ9&!CVE5Y9l2>2s~%2&&yv(MLFybY=Z(kJ%1E((X$$<jB;$Qg1vkfY_p@J(kxW|>v&}r*ww+_~f&iTXMQkUG-3voY`OZ*P!_nJ@Rc+VFpUoSss%#C<^6acNx=~Q4*PrlxC;o)fM)$fx5+_aK-iVNjW}9?fLN)y$PcQ8@skw8g!H8EfCWTT=Z7Q$<XMvjv8x-v}4gNJa5!-Qc9Ot2t&}e`FVi;cSO7VS7VeK}+PG|=hycfo977~<OL4mu(?D(={EK7gMjaY{zI&5cWZEk<L!bguhWXHncVZr?+SV=dkj}@6C5BAJbP#bi<NhxHEGb|X_Y75d<3o7PadXqd`Wt;zugo%Qt5@<2N5S*As-W@6GxhFVXi4>c2`5>ufF-UP!x=CTuQ@YVhQKuHPi^_}0`MNy#7`#zpL$nlAx`t~!uNK!Ag2LUpy}%!FbG|z)g}G^pKC=Y&$dmRux~8wP*Szn1=!UzarNwD14}GVy`?-AZtJ#B}Tv1@?F@m$3aV*+aKo4FNu#<iPJ~tK4y+%+KOG14HU|$_93A;TWbCFjc8AaRMlXZ_CNh?MOrKSZvj)E(M3P^#_i#Q`|&^>o8+3>e)ZR4W0f_)>ZIUfhAxn(12=*#9a$v)#Rmekh2A<o?u9I~2qSz7kHUV{OLfxtsu7`7e+;dCZ698#d6u$Q2Uc=9RftS8*Dkk6u?CljFF9vKlzxd7GrVuEXlwTHFDV~-8|-H|;pP#5Bon-VODeE@r+q{9HXw}A~1sd)N54m6NDK{nVc(xC0$GKnEcj809Q?XD!zwLvGOH>ik-L0Lzn=1rRVW4Eb7M3Xe-v>|C4c~!!A4;)U4Bp@`mO`@MfHCAJKJ5K8~xx~Qrm`Mi(1vFQq1s<Km(yVcL3rzGt2u=K{;{<eaU6|@c)ikL|wG!<$z~#ju6XtK0eDH>G#2tSQ!#xu1*$H+U!0ZO>Z)>Xb+S*uvZqsJV>*(CaX58svVW0pNgg6-WE~zj~;HRq5?tX&u2#KtBuuN<KQ{nJ5%%veh>VSeT$+AY8f^@8LH-@3vODL}EDOBcBCmWTO;B$Uw3FqFJ@#r@=kngo0D6ftxsOtNLkD!M!6kymkTVByU$Ekf_2KaZKY^O?5;6}0K3Ui?(60t;`mO%cum~|{HOurGyDFZ@q07Tz5=VtD@Ig{<-I>q$iI<zA~@{K&5#__RzVY!1}xa}3T%6w<h1eG};;zRCEy<8Z!Nw52%R>H;QRvjFNTOnm}cE`*|$FAZY3{6#Yd7d*&U;)MAqB!=O*s1ax0GAC`x3kuPKkZj%{vj<R7)Y~s=e!XCDYv{N#3<s9%kEdSxF4=&arUo~+ogfI!gP#GW>X<G#ryC9-k#RFNWTGyDI%)(<2!Lan@8rz1Tv0Z{4b#-VlrF8sL9qK1;G*k2LH{4C1SA?WP&<F0Aerg467E8Y<IoDMQHSRM`t^o<_H6|#M3}sw-rj13ul&y1C<}LpTE$Kb~>6J+_ZNpMjH9&-9s~r1CToBWqdeZVF${+|47%=<V8C4FBGfy9^YQ&4W%Do**SP?&xulUs5;cg{ViH0VP39vM3m|oPnR{4m{I!<@WMkPsAKbuO7Ne^-+=yD+Kgaqr0i<;C*=08&3)8Z1IOh(GFhi^t1TY&#fd#;%jn{@DLep(Cqjf91S)hY>>O)il3BnSl6av?OIW&{#Uvded+NmLX-w5qJ1MYNhuM0#|MGCHVtSyKIZ^hpJfmUX(J=2H--$7MSDleU?2FM3-#CcAOr6F^Sp{A`-9qrCg$#c9oJ<Tdp9-e^|4R*%1{(+m(S|y0-1+qfIPJT6Fdg}aza_sNtK9|j9jD&~AMV%iokQs<1!IWK@S3e-H_Rl`3zPYc*MrM!-X&c?2kJ#fvz|QueeiQtV^$WO(G<67ws;a1vrURV0=iHXV2&=8t%7Pj0Lk7#p*$rMjsQ?z%{J*(A0ER`-68Zb=6Dm~%zK>OK|dY<JP3u8zUWXWT{!4PM~Az&Ibd`}>fIb-_RX20KYqIeFij&jq7I|Db0uY|^L;Lhd`n_Dr7JGcKu{O=$l@LxC&^JWMg0mk4!W<xm+68db%Kr43$58-$(rc0(l^2BQ)K&-VS1|~+cs*IZt`;1(!O>iR4-nOVU>)&<PRr<AoK>J?DR36q3pmO<L2X!@h}=~=Aj^B(Gv+d)}Se_b^spVt@MJeJuB-PBngIC`Hb9nf5nGQ#bb@yuQ6_2kdZB0-vjYv_xa@X>1+|l2Y^rzX%C2{Is!m3J%GdX2ml?fKw@?H<Um`;CfLqB4Y#=;e5(yyqlB1MhS{idny`Oo6{l=|C*}_<Cc(V-oeR%?W1O=29ru6!Ek1p_m?clv_h2Nr_e*8o9)vX&kfx@ErtJK#L*iL7UEgmG0tDhhGe===a$uRPi(PZIXEVFA5#4bZ#`48dd5>f&xd_t`h&^lFu5WQpwtJTL;KDw%n2%k+p>s#Q5s&(d(x<_wzvw)wbW!asszYMDd-iu=RrKf^j}9z~b@=PES1+G4rRLgq2>Oeom+*j>K!-YR4R|yeS_I7a9%ZOn?|K+%ZWoO)n|wMJ<Aq_y-P!Vv;B}qdp9XzkU)k>Qk~?quO^m}#|NDNB8;aS}{KBC~r|-?#e+GX#d;g&`f1S3&^CW#j?~J=<DBOkTJOgfv!NwsB(@_SqK;C$kd!{Cd@4i#>Znx9|Hu)I3E8dY6s=J4wTK$;P(Ch9>*8Q#qHl6khiGObO#$U6i!zcEZSM0@-1mt|>bk`W#ti$eyIZ#60Sy_3Xx-D}$CPT0iIt9?|*6aLp6ehpr+rezChidQ2A}_Bad!+}=`Gl@K=|+@&QU3-bKEzgIyR+}*))b*4o|Yu|6W+#f+xN45O@Fpkg8%#SEmk{#vyJ!`>>iCeXXn*s+urht+sL~oV7m4ac-jw0P?Ei7IE|r8$E%NjW+eyC#7U}ERcx=oJyzsbRJG0*=zZfu9xV7<-ZnWdoz1Sy`Ec4pO}5*n*=~>N;a(=;lo=7+Na!{yrzbsMa7H(sn2<;3awa^OhIDo~52*#|%W0Fsv)5qZ5(eAsTbzUsFKX;djqK7Y(#<#Sv6EG?;gdhqE!JOj6R=RFp@b@j@}Y{4kRT7un5_3AJu877&V{Pcfj?i61XWT*604WE)>Jazny3|SVMwmW@OHHS9*0R{h0GGl+haN@h5FpOC(aP&<s!2WRC6$In7h60r8zv5pX<y~+)K{o0q7^^(uw?Brhuacv{)o~2@b?PW_89Sz>#Yh`+#+h&;$4QWYP_;y*CM$f3wBm=VuLGhj(5=bCEFwbHm>U`-&+&`uXhX$;m<_FPEVxoh(HUYEQNlnNpa$txVJ~xHBW0vAMwsH8_GT6K1%`v?Wh`FLUn5N!!a^LlY&E4RyeoWKjp^$~G4D_orI(r%NC<)S40QCjlA;A}DHmA0VkqY~<0@4Z{%il5X1K*EevRl(YkFhQ3$yV=<gGN9O{4C~1!APGj5|gO>!yViqqt>2geKpQZL>&~fK##kjz3YW40@BvBgE1=TpluarchGf!?hl8wEYbZl#X>i4p1Ep5$5<&M9%Axx#t<%@0xP#4qvpSwtL{M7=7XMEsru&C8N9PFJ*Ieg%S(p?N+A<$Q*yf3Bv@xXPc8_M-=Hu=1(RsHiS<OR45$rIMY`u>6FxD%1r$5-aZ-DEiDUS_(t?*!aMeDIpW^z@HkanIrKHHjmxH^?VVPGf*Dmv{E$5@4?=j)(7LE%BQv41`aEooHsT-+SY1b4P8C<B3F_Y3JxRH6{?pgQG{aa9`m-N5WXe!)^q5ZX%tOV-kJb00Zwn;~1c93xlOrWVn!rt^6Pi{mBpwj<1QOLARI^jR{NOaE@_{cHC0{Une{f{vk6p?(L!*YY;z8ps9PW^MXm$XLY|$(jrU^ZQ_L9^&M)d*%QM;EQjQP;*QelRThI3hI_sN5nSi(trgmvP2~4C_8}&uu;@#EQRh^Eui75A0DNhMDKTr4H{_BW6o=lqguMV$aW<JQ`q!<QS_MoN31CkLU#el{JJ>kI<w(XY{@~HU51_^Bvp*g}du+}pPy#+($G}?j<9h@Y{J$L8LiQMQ0#gqO(v2q_G?)3duE0(+pr*+QFp~ogVB7;kNPHNp<>mAQFU{^YeYL>gU@D60@-!kKc<yC1v`c)5Fz2)B$-+@*XwR}ktph?{XKpp$EAhWs0|2(<ZU=9k|NLi4m#XliZ?tAPXJiLhv)gh?Rr85c`T`hzFZL?CQ2~B6*D@0)pxi3M<^G<1X^6@DWAxOCxOytV=&2q(hIcKG+=w*C$DpSEwWpqQ8)j~q?yakt(aI={xBeqcFa?McT<0*29J<l-sbe3e`M#Y&4!L?9Zvw8wSHq32@;1%dbgFL>00-!BIB_awXK_zI!Q$B4y9V_1NI*{?0yI527NwKDpgN12=E!@qryVk(#eq4pU-SOJ`f97~=?P_jq?LPmvgkygoQ3lLIs=~{&$x>{aEV&S0;S4_A<<O?0>eUNkMbi)yNHhge!uTNusLR`6GNYOGr5j>B3`Ge^@LdW)D^rt=ZRj}<5rZF0GXc(&Gb^aesEbO-6nzk#By(I_koSu2lyv+cb@3WLV^sP#TdT(_x^E*a~gz|Jqt-139EMu0-!xT4DIQcL8B#p2)UClf%p2|yFK8#qUZ~Nq88qdr;t_0!MyKthbM^a+pbMMP=En~gEsD17{)^>k^F6)QEvy-M{#H)RJaphe{Hhit<WA|e*r!K*jC;Lni6~NX{?2Plag?u&BG#$zw}$QVrD)6)?*d@ZP!mgZ6!}|Q*P^lkJW-D8h*6b(|C8&e30e9*5^p%GPO;<G?%Hp%iB+2>Wa_J#xy$Xc4s*BYIOWb${<I+eMe9V3i@2N*t7X72FEzb3I6%7uQ4O;*>jjmqBl8&?n|8{s+HW)VB9~JLj;oBrtdRM?<1OOwkC+ci4#7c&0Ecw=svXj)Ui!(iO2B$h@#FC;eCSHycaPIvy&~i1yxfOH%iu*``rDl?@kNe=*0<4SM@D^huS8ESmFBHm0osrL*%d9QorNg?n9f{P{XrZ=tM`%0&NN~_Ko*|^jCjz7fT{H^by4~f;F6*S%bX~vI65Nx9*drI_dr|03-|6K%}eSFZ69w@ShvJt%?V!F_jWIWS#GP5c-tVW>@};PR^gLReQ_vW%|McUSk4R81oCt>-D`)f9Qc9d+px)Hq(6I8@S!Ln9HMT6R;X}BogKx`4z1JCLN3Kxj8gsmWX4s2h!H@{#>wb94^pf?=Q^<?=!^%xhn^>OQ*sfz2byYmww*a6jR8bkL6ggck{Tj-g@6w{a8MK_kV(Szq|?FK70TE?D<R+HkdyBhQG7INyljE6h-jE>G<jNsmnEv`?Q=!ISIRFL-+=SZmn>cBU?8ZZNvi-2n&@6Ebzd7qFy%VsB$+yg-xz1_FoK(j7R?Um(J8lK5)G-8OJ@7-p?r!dvt8B^DPB39VO-Det7rn<(rpp{+vFjC5})Ff|6o~95LAPM{ID*9eGIC_dgBT*{&ig32J((Bgf2vl&~*Fw<1haR3vE{ny=f^<*xq*zzz~T"""


def _trainer_source(lam: float) -> str:
    import base64, hashlib, zlib
    raw = zlib.decompress(base64.b85decode(PAYLOAD.encode("ascii")))
    actual = hashlib.sha256(raw).hexdigest()
    if actual != EXPECTED_SHA256:
        raise RuntimeError(f"Trainer hash mismatch: {actual} != {EXPECTED_SHA256}")
    source = raw.decode("utf-8")
    old = "    splade_lambda = 1e-4\n"
    new = f"    splade_lambda = {lam!r}\n"
    if source.count(old) != 1:
        raise RuntimeError("Could not locate the single original splade_lambda assignment")
    source = source.replace(old, new, 1)

    # A100 screening optimization: disable gradient checkpointing.
    # This changes only the compute/memory strategy, not the model objective.
    old_gc = (
        '        if hasattr(self.model, \"gradient_checkpointing_enable\"):\n'
        '            self.model.gradient_checkpointing_enable()\n'
        '        if hasattr(self.model.config, \"use_cache\"):\n'
        '            self.model.config.use_cache = False\n'
    )
    new_gc = (
        '        # Gradient checkpointing disabled for A100 screening.\n'
        '        if hasattr(self.model.config, \"use_cache\"):\n'
        '            self.model.config.use_cache = False\n'
    )
    if source.count(old_gc) != 1:
        raise RuntimeError("Could not locate gradient-checkpointing block")
    source = source.replace(old_gc, new_gc, 1)
    return source


def _extract_data(dest):
    from pathlib import Path
    import zipfile
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    zip_path = Path("/vol/modal_splade_data.zip")
    if not zip_path.exists():
        raise FileNotFoundError("/vol/modal_splade_data.zip not found in Modal Volume")
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(dest)
    return dest


@app.function(
    image=image,
    volumes={"/vol": volume},
    timeout=30 * 60,
    cpu=2.0,
    memory=8192,
)
def validate_data():
    from pathlib import Path
    import subprocess, sys, shutil

    root = Path("/tmp/modal_splade_validation")
    if root.exists():
        shutil.rmtree(root)
    input_root = _extract_data(root / "input")
    output_root = root / "output"
    output_root.mkdir(parents=True, exist_ok=True)

    trainer = root / "trainer.py"
    trainer.write_text(_trainer_source(0.1), encoding="utf-8")

    cmd = [
        sys.executable, str(trainer),
        "--seed", "42",
        "--split-seed", "42",
        "--input-root", str(input_root),
        "--output-root", str(output_root),
        "--num-workers", "0",
        "--dry-run",
    ]
    subprocess.run(cmd, check=True)
    return "Data validation passed: 7,944 queries / 62,515 triplets / query-disjoint split."


@app.function(
    image=image,
    gpu="A100-40GB",
    volumes={"/vol": volume},
    timeout=6 * 60 * 60,
    cpu=4.0,
    memory=16384,
    max_containers=2,
)
def train_lambda(lam: float):
    # Screening acceleration only: batch 16 x grad-accum 2 = effective batch 32.
    # Gradient checkpointing is disabled to use the A100 memory instead of recompute.
    from pathlib import Path
    import json, shutil, subprocess, sys, pandas as pd

    label = (f"{lam:g}".replace(".", "p").replace("-", "m"))
    final_dir = Path("/vol/lambda_sweep") / f"lambda_{label}_seed42"
    if final_dir.exists() and any(final_dir.iterdir()):
        raise RuntimeError(f"{final_dir} already exists; refusing to overwrite it.")

    root = Path("/tmp") / f"splade_lambda_{label}"
    if root.exists():
        shutil.rmtree(root)
    input_root = _extract_data(root / "input")
    output_root = root / "output"
    output_root.mkdir(parents=True, exist_ok=True)

    trainer = root / "splade_bottom15_multiseed.py"
    trainer.write_text(_trainer_source(lam), encoding="utf-8")

    print("=" * 80, flush=True)
    print(f"STARTING lambda={lam:g} on seed=42 / split-seed=42", flush=True)
    print("=" * 80, flush=True)

    cmd = [
        sys.executable, str(trainer),
        "--seed", "42",
        "--split-seed", "42",
        "--input-root", str(input_root),
        "--output-root", str(output_root),
        "--batch-size", "16",
        "--grad-accum", "2",
        "--num-workers", "4",
        "--skip-eval",
    ]
    subprocess.run(cmd, check=True)

    run_dir = output_root / "splade_bottom15_seed42"
    history_path = run_dir / "training_history.csv"
    if not history_path.exists():
        raise RuntimeError(f"Missing training history: {history_path}")

    hist = pd.read_csv(history_path)
    valid = hist[hist["kind"] == "validation"].copy()
    if valid.empty:
        raise RuntimeError("No validation rows were produced")

    best_ce = valid.sort_values(["ce", "epoch", "global_step"]).iloc[0]
    best_total = valid.sort_values(["loss", "epoch", "global_step"]).iloc[0]
    summary = {
        "lambda": float(lam),
        "seed": 42,
        "best_validation_ce": float(best_ce["ce"]),
        "best_ce_epoch": int(best_ce["epoch"]),
        "best_ce_step": int(best_ce["global_step"]),
        "l1_at_best_ce": float(best_ce["l1"]),
        "lambda_times_l1_at_best_ce": float(lam * best_ce["l1"]),
        "best_total_loss": float(best_total["loss"]),
        "best_total_epoch": int(best_total["epoch"]),
        "best_total_step": int(best_total["global_step"]),
    }
    (run_dir / "lambda_screening_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )

    final_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(run_dir, final_dir)
    volume.commit()

    print(f"FINISHED lambda={lam:g}", flush=True)
    print(json.dumps(summary, indent=2), flush=True)
    print(f"Saved to {final_dir}", flush=True)
    return summary


@app.local_entrypoint()
def main():
    print("Checking the uploaded training package first...")
    print(validate_data.remote())
    print("\nLaunching ONE A100: lambda=3.0 (batch 16, grad-accum 2, no checkpointing)\n")

    result = train_lambda.remote(3.0)

    print("\n" + "=" * 80)
    print("LAMBDA=3 RUN FINISHED")
    print("=" * 80)
    print(result)
    print("\nResult is persisted in Modal Volume 'splade-data' under /lambda_sweep/lambda_3_seed42")
