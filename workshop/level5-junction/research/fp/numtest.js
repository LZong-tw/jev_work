let s=12345; const r=()=>{s=(s*1103515245+12345)%2147483648; return s/2147483648;};
const out=[];for(let i=0;i<200000;i++){const a=(r()-0.5)*300,b=(r()-0.5)*300,x=r()*3,y=r()*50;out.push([a,b,Math.hypot(a,b),x,Math.pow(x,4),y,Math.pow(y,2)]);}
console.log(JSON.stringify(out));
